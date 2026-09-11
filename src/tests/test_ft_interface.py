#!/usr/bin/env python3
"""
Hardware-independent tests for the ATI Mini45 / NI DAQ F/T pipeline.

Every test runs with no NI device present and creates no DAQ task (Test F).
The real FT29831.cal is used where the point is that the real file parses;
everything else uses synthetic fixtures so the expected numbers are known
exactly rather than compared against whatever the hardware happened to emit.

    /usr/bin/python3 -m unittest discover -s tests -v

Interpreter note: nidaqmx and numpy for this project live under
/usr/bin/python3, not the anaconda python that is first on PATH.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vbts_platform.ati_calibration import (  # noqa: E402
    GAUGE_NAMES,
    NUM_GAUGES,
    SENSOR_FRAME,
    WRENCH_AXES,
    ATICalibration,
    CalibrationError,
    force_factor_to_newton,
    torque_factor_to_newton_metre,
)
from vbts_platform.ft_interface import (  # noqa: E402
    ChannelMappingError,
    FTError,
    FTInterface,
    NotConnectedError,
    load_calibration,
    load_ft_config,
)

REAL_CAL = PROJECT_ROOT / "src" / "config" / "FT29831.cal"


def write_cal(body: str | None = None, *, serial: str = "FT00001", num_gages: str = "6",
              force_units: str = "N", torque_units: str = "N-m",
              user_rows: dict | None = None) -> Path:
    """Write a synthetic ATI-format calibration file; return its path."""
    if user_rows is None:
        user_rows = {a: [1.0 if i == j else 0.0 for j in range(6)]
                     for i, a in enumerate(WRENCH_AXES)}
    user_xml = "".join(
        f'<UserAxis Name="{a}" values="{" ".join(str(v) for v in user_rows[a])}" max="10"/>'
        for a in WRENCH_AXES if a in user_rows)
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<FTSensor Serial="{serial}" BodyStyle="Mini45" Family="DAQ" '
        f'NumGages="{num_gages}" CalFileVersion="1.1">'
        f'<Calibration PartNumber="SI-145-5" CalDate="1/1/2020" '
        f'ForceUnits="{force_units}" TorqueUnits="{torque_units}" DistUnits="m" '
        f'OutputMode="Ground Referenced Differential" OutputRange="20" '
        f'HWTempComp="True" GainMultiplier="1" OutputBipolar="True">'
        f'<BasicTransform Dx="0" Dy="0" Dz="0" Rx="0" Ry="0" Rz="0"/>'
        f'{user_xml}</Calibration></FTSensor>')
    if body is not None:
        xml = body
    fh = tempfile.NamedTemporaryFile("w", suffix=".cal", delete=False)
    fh.write(xml)
    fh.close()
    return Path(fh.name)


def make_ft(cal=None, channels=None, **kw) -> FTInterface:
    # `channels is None` rather than a truthiness test: an empty list is a
    # meaningful input here (it must be rejected), not a request for defaults.
    if channels is None:
        channels = [f"Dev1/ai{i}" for i in range(1, 7)]
    return FTInterface(cal or ATICalibration.from_file(REAL_CAL), "Dev1", channels, **kw)


# ===========================================================================
# Test A — calibration parser
# ===========================================================================

class TestA_CalibrationParser(unittest.TestCase):

    def test_real_file_present(self):
        self.assertTrue(REAL_CAL.is_file(), f"{REAL_CAL} missing")

    def test_parses_ft29831(self):
        c = ATICalibration.from_file(REAL_CAL)
        self.assertEqual(c.serial, "FT29831")
        self.assertEqual(c.body_style, "Mini45")
        self.assertEqual(c.family, "DAQ")
        self.assertEqual(c.part_number, "SI-145-5")
        self.assertEqual(c.cal_date, "1/8/2020")
        self.assertEqual(c.num_gauges, 6)
        self.assertEqual(c.force_units, "N")
        self.assertEqual(c.torque_units, "N-m")
        self.assertEqual(c.dist_units, "m")
        self.assertEqual(c.output_mode, "Ground Referenced Differential")

    def test_matrix_shape_and_finite(self):
        c = ATICalibration.from_file(REAL_CAL)
        self.assertEqual(c.user_matrix.shape, (6, 6))
        self.assertTrue(np.all(np.isfinite(c.user_matrix)))

    def test_matrix_rows_match_file_exactly(self):
        c = ATICalibration.from_file(REAL_CAL)
        np.testing.assert_allclose(
            c.user_matrix[0],
            [-0.04294, -0.01144, 2.35717, -24.09445, -1.78834, 23.72887], atol=1e-9)
        np.testing.assert_allclose(
            c.user_matrix[2],
            [34.41401, 1.73873, 33.73050, 1.53595, 33.62034, 1.17777], atol=1e-9)
        np.testing.assert_allclose(
            c.user_matrix[5],
            [0.05077, -0.35302, 0.02456, -0.35341, 0.01811, -0.34542], atol=1e-9)

    def test_basic_transform(self):
        c = ATICalibration.from_file(REAL_CAL)
        self.assertAlmostEqual(c.basic_transform["Dz"], 0.006858, places=9)
        self.assertAlmostEqual(c.basic_transform["Dx"], 0.0)
        self.assertAlmostEqual(c.basic_transform["Dy"], 0.0)

    def test_max_loads(self):
        c = ATICalibration.from_file(REAL_CAL)
        self.assertEqual(c.max_loads["Fx"], 145.0)
        self.assertEqual(c.max_loads["Fy"], 145.0)
        self.assertEqual(c.max_loads["Fz"], 290.0)
        self.assertEqual(c.max_loads["Tz"], 5.0)

    def test_internal_consistency(self):
        # UserAxis must equal Axis/scale with BasicTransform applied. This is
        # the parser proving it read scales, ordering and the transform right.
        self.assertTrue(ATICalibration.from_file(REAL_CAL).verify_internal_consistency())

    def test_serial_mismatch_rejected(self):
        with self.assertRaises(CalibrationError):
            ATICalibration.from_file(REAL_CAL, expected_serial="FT99999")

    def test_serial_match_case_insensitive(self):
        self.assertEqual(
            ATICalibration.from_file(REAL_CAL, expected_serial="ft29831").serial, "FT29831")

    def test_metadata_complete(self):
        md = ATICalibration.from_file(REAL_CAL).metadata()
        for k in ("serial", "cal_date", "native_force_unit", "native_torque_unit",
                  "basic_transform", "matrix_source", "user_matrix",
                  "internally_consistent", "frame", "gauge_order"):
            self.assertIn(k, md)
        self.assertEqual(md["frame"], SENSOR_FRAME)
        self.assertEqual(md["matrix_source"], "UserAxis")
        self.assertEqual(md["gauge_order"], list(GAUGE_NAMES))

    def test_exceeds_max_load(self):
        c = ATICalibration.from_file(REAL_CAL)
        self.assertEqual(c.exceeds_max_load([0, 0, 0, 0, 0, 0]), {})
        over = c.exceeds_max_load([200.0, 0, 0, 0, 0, 0])
        self.assertIn("Fx", over)


# ===========================================================================
# Test B — synthetic voltage -> wrench conversion
# ===========================================================================

class TestB_Conversion(unittest.TestCase):

    def test_identity_passes_through(self):
        p = write_cal()
        try:
            c = ATICalibration.from_file(p)
            v = np.array([1., 2., 3., 4., 5., 6.])
            np.testing.assert_allclose(c.to_wrench(v), v)
        finally:
            p.unlink()

    def test_known_matrix_known_answer(self):
        rows = {a: [0.]*6 for a in WRENCH_AXES}
        rows["Fx"] = [2., 0, 0, 0, 0, 0]
        rows["Fz"] = [0, 0, 3., 0, 0, 0]
        rows["Ty"] = [0, 0, 0, 0, -4., 0]
        p = write_cal(user_rows=rows)
        try:
            w = ATICalibration.from_file(p).to_wrench([1., 9., 2., 9., 0.5, 9.])
            self.assertAlmostEqual(w[0], 2.0)
            self.assertAlmostEqual(w[2], 6.0)
            self.assertAlmostEqual(w[4], -2.0)
            self.assertAlmostEqual(w[1], 0.0)
        finally:
            p.unlink()

    def test_bias_subtraction(self):
        p = write_cal()
        try:
            c = ATICalibration.from_file(p)
            v = np.array([1., 2., 3., 4., 5., 6.])
            b = np.array([0.5]*6)
            np.testing.assert_allclose(c.to_wrench(v, bias=b), v - 0.5)
        finally:
            p.unlink()

    def test_block_matches_per_sample(self):
        c = ATICalibration.from_file(REAL_CAL)
        blk = np.random.default_rng(0).normal(size=(6, 20))
        got = c.to_wrench(blk)
        self.assertEqual(got.shape, (6, 20))
        for i in range(20):
            np.testing.assert_allclose(got[:, i], c.to_wrench(blk[:, i]), atol=1e-12)

    def test_block_bias_broadcasts(self):
        c = ATICalibration.from_file(REAL_CAL)
        blk = np.ones((6, 5))
        b = np.full(6, 0.25)
        np.testing.assert_allclose(
            c.to_wrench(blk, bias=b)[:, 0], c.to_wrench(np.full(6, 0.75)), atol=1e-12)

    def test_zero_gives_zero(self):
        c = ATICalibration.from_file(REAL_CAL)
        np.testing.assert_allclose(c.to_wrench(np.zeros(6)), np.zeros(6), atol=1e-15)

    def test_linearity(self):
        c = ATICalibration.from_file(REAL_CAL)
        a, b = np.arange(6.), np.arange(6.)[::-1].copy()
        np.testing.assert_allclose(c.to_wrench(a+b), c.to_wrench(a)+c.to_wrench(b), atol=1e-12)

    def test_fz_from_a_pure_gauge_response(self):
        # Sanity: the Fz row is dominated by the odd gauges (34.4, 33.7, 33.6)
        # so a uniform 1 V on all six gauges must give a large positive Fz.
        c = ATICalibration.from_file(REAL_CAL)
        self.assertGreater(c.to_wrench(np.ones(6))[2], 100.0)

    def test_wrong_length_rejected(self):
        c = ATICalibration.from_file(REAL_CAL)
        for bad in (np.zeros(5), np.zeros(7)):
            with self.assertRaises(ValueError):
                c.to_wrench(bad)

    def test_nan_rejected(self):
        c = ATICalibration.from_file(REAL_CAL)
        with self.assertRaises(ValueError):
            c.to_wrench([1., 2., np.nan, 4., 5., 6.])
        with self.assertRaises(ValueError):
            c.to_wrench(np.zeros(6), bias=np.array([np.nan]*6))


# ===========================================================================
# Test C — channel ordering
# ===========================================================================

class TestC_ChannelOrdering(unittest.TestCase):

    def test_permutation_changes_result(self):
        c = ATICalibration.from_file(REAL_CAL)
        v = np.array([0.10, -0.20, 0.30, -0.40, 0.50, -0.60])
        self.assertGreater(
            np.max(np.abs(c.to_wrench(v) - c.to_wrench(v[[1, 0, 2, 3, 4, 5]]))), 1e-6)

    def test_reversal_changes_result(self):
        c = ATICalibration.from_file(REAL_CAL)
        v = np.array([0.10, -0.20, 0.30, -0.40, 0.50, -0.60])
        self.assertGreater(
            np.max(np.abs(c.to_wrench(v) - c.to_wrench(v[::-1].copy()))), 1e-6)

    def test_order_preserved_verbatim(self):
        chans = ["Dev1/ai5", "Dev1/ai3", "Dev1/ai1", "Dev1/ai4", "Dev1/ai2", "Dev1/ai6"]
        self.assertEqual(make_ft(channels=chans).channels, chans,
                         "channel order must never be sorted or normalised")

    def test_gauge_map_is_positional(self):
        chans = [f"Dev1/ai{i}" for i in range(1, 7)]
        self.assertEqual(make_ft(channels=chans).gauge_map,
                         {"SG0": "Dev1/ai1", "SG1": "Dev1/ai2", "SG2": "Dev1/ai3",
                          "SG3": "Dev1/ai4", "SG4": "Dev1/ai5", "SG5": "Dev1/ai6"})

    def test_wrong_count_rejected(self):
        for bad in ([], ["Dev1/ai0"], [f"Dev1/ai{i}" for i in range(7)]):
            with self.assertRaises(ChannelMappingError):
                make_ft(channels=bad)

    def test_duplicates_rejected(self):
        with self.assertRaises(ChannelMappingError):
            make_ft(channels=["Dev1/ai1"]*6)

    def test_config_channel_count_is_six(self):
        cfg, _ = load_ft_config()
        self.assertEqual(len(cfg["daq"]["channels"]), NUM_GAUGES)
        self.assertEqual(len(set(cfg["daq"]["channels"])), NUM_GAUGES)


# ===========================================================================
# Test D — tare
# ===========================================================================

class TestD_Tare(unittest.TestCase):

    def setUp(self):
        self.cal = ATICalibration.from_file(REAL_CAL)
        self.ft = make_ft(self.cal)

    def test_starts_untared(self):
        self.assertFalse(self.ft.is_tared)
        self.assertIsNone(self.ft.tare_wrench)
        self.assertIsNone(self.ft.tare_volts)

    def test_set_and_subtract(self):
        v0 = np.array([1.1, 1.2, 0.8, 1.0, 1.1, -1.5])
        self.ft.set_tare_from_volts(v0)
        self.assertTrue(self.ft.is_tared)
        np.testing.assert_allclose(self.ft.tare_wrench, self.cal.to_wrench(v0), atol=1e-12)
        # dW at the tare point must be exactly zero
        np.testing.assert_allclose(self.cal.to_wrench(v0, bias=v0), np.zeros(6), atol=1e-12)

    def test_delta_is_exact(self):
        v0 = np.array([1.1, 1.2, 0.8, 1.0, 1.1, -1.5])
        v1 = v0 + np.array([0.01, -0.02, 0.03, 0.0, 0.005, -0.004])
        self.ft.set_tare_from_volts(v0)
        np.testing.assert_allclose(
            self.cal.to_wrench(v1, bias=v0),
            self.cal.to_wrench(v1) - self.cal.to_wrench(v0), atol=1e-12)

    def test_clear(self):
        self.ft.set_tare_from_volts(np.ones(6))
        self.ft.clear_tare()
        self.assertFalse(self.ft.is_tared)
        self.assertIsNone(self.ft.tare_volts)

    def test_accessors_return_copies(self):
        self.ft.set_tare_from_volts(np.ones(6))
        got = self.ft.tare_wrench
        got[0] = 999.0
        self.assertNotAlmostEqual(self.ft.tare_wrench[0], 999.0)
        gv = self.ft.tare_volts
        gv[0] = 999.0
        self.assertAlmostEqual(self.ft.tare_volts[0], 1.0)

    def test_invalid_rejected(self):
        for bad in (np.ones(5), np.array([1., 2., 3., 4., 5., np.nan])):
            with self.assertRaises(ValueError):
                self.ft.set_tare_from_volts(bad)

    def test_tare_requires_connection(self):
        with self.assertRaises(NotConnectedError):
            self.ft.tare(0.01)


# ===========================================================================
# Test E — invalid calibration handling
# ===========================================================================

class TestE_InvalidCalibration(unittest.TestCase):

    def _expect_error(self, **kw):
        p = write_cal(**kw)
        try:
            with self.assertRaises(CalibrationError):
                ATICalibration.from_file(p)
        finally:
            p.unlink()

    def test_missing_file(self):
        with self.assertRaises(CalibrationError):
            ATICalibration.from_file(PROJECT_ROOT / "nope.cal")

    def test_malformed_xml(self):
        self._expect_error(body="<FTSensor><Calibration>truncated")

    def test_wrong_root(self):
        self._expect_error(body='<?xml version="1.0"?><NotASensor/>')

    def test_no_calibration_element(self):
        self._expect_error(body='<?xml version="1.0"?><FTSensor Serial="X" NumGages="6"/>')

    def test_wrong_gauge_count(self):
        self._expect_error(num_gages="3")

    def test_missing_axis_row(self):
        rows = {a: [1.]*6 for a in WRENCH_AXES}
        rows.pop("Tz")
        self._expect_error(user_rows=rows)

    def test_bad_row_length(self):
        rows = {a: [1.]*6 for a in WRENCH_AXES}
        rows["Fy"] = [1.]*4
        self._expect_error(user_rows=rows)

    def test_nan_in_matrix(self):
        rows = {a: [1.]*6 for a in WRENCH_AXES}
        rows["Fz"] = [1., 2., float("nan"), 4., 5., 6.]
        self._expect_error(user_rows=rows)

    def test_non_numeric(self):
        rows = {a: [1.]*6 for a in WRENCH_AXES}
        rows["Fx"] = ["oops", 2., 3., 4., 5., 6.]
        self._expect_error(user_rows=rows)

    def test_missing_units(self):
        self._expect_error(force_units="", torque_units="")

    def test_unknown_units(self):
        self._expect_error(torque_units="dyne-cm")

    def test_missing_serial(self):
        self._expect_error(serial="")

    def test_unit_helpers_reject_unknown(self):
        with self.assertRaises(CalibrationError):
            force_factor_to_newton("furlongs")
        with self.assertRaises(CalibrationError):
            torque_factor_to_newton_metre("dyne-cm")


class TestUnits(unittest.TestCase):

    def test_real_file_is_si(self):
        c = ATICalibration.from_file(REAL_CAL)
        self.assertEqual(c.force_to_newton, 1.0)
        self.assertEqual(c.torque_to_newton_metre, 1.0)
        np.testing.assert_allclose(c.si_matrix, c.user_matrix)

    def test_lbf_converted(self):
        p = write_cal(force_units="lbf")
        try:
            c = ATICalibration.from_file(p)
            self.assertAlmostEqual(c.force_to_newton, 4.4482216152605, places=12)
            self.assertAlmostEqual(c.to_wrench([1., 0, 0, 0, 0, 0])[0],
                                   4.4482216152605, places=10)
        finally:
            p.unlink()

    def test_lb_in_converted(self):
        p = write_cal(torque_units="lb-in")
        try:
            c = ATICalibration.from_file(p)
            expected = 4.4482216152605 * 0.0254
            self.assertAlmostEqual(c.to_wrench([0, 0, 0, 1., 0, 0])[3], expected, places=12)
            np.testing.assert_allclose(c.si_matrix[:3], c.user_matrix[:3])
        finally:
            p.unlink()

    def test_separator_and_case_insensitive(self):
        for u in ("N-m", "n-m", "NM", "N_m", " N-M "):
            self.assertAlmostEqual(torque_factor_to_newton_metre(u), 1.0)


# ===========================================================================
# Test F — importable and usable with no NI device
# ===========================================================================

class TestF_HardwareIsolation(unittest.TestCase):

    def test_modules_import_without_ni(self):
        import importlib
        for name in ("vbts_platform.ati_calibration", "vbts_platform.ft_interface"):
            self.assertIsNotNone(importlib.import_module(name))

    def test_calibration_module_does_not_import_nidaqmx(self):
        # nidaqmx is imported lazily inside connect(), so the whole calibration
        # path works on a machine with no NI stack at all.
        src = (PROJECT_ROOT / "src" / "vbts_platform" / "ati_calibration.py").read_text()
        self.assertNotIn("import nidaqmx", src)

    def test_full_conversion_without_hardware(self):
        ft = make_ft(channels=[f"NoDev/ai{i}" for i in range(6)])
        self.assertFalse(ft.connected)
        self.assertEqual(ft.calibration.to_wrench(np.full(6, 0.1)).shape, (6,))

    def test_reads_without_connect_raise(self):
        ft = make_ft()
        for call in (ft.read_raw, lambda: ft.read_wrench(),
                     lambda: ft.acquire_baseline(0.01),
                     lambda: ft.check_channel_health(0.01)):
            with self.assertRaises(NotConnectedError):
                call()

    def test_baseline_starts_empty(self):
        self.assertIsNone(make_ft().get_baseline())

    def test_bad_settings_rejected_before_hardware(self):
        with self.assertRaises(FTError):
            make_ft(sample_rate_hz=0)
        with self.assertRaises(FTError):
            make_ft(samples_per_read=0)


# ===========================================================================
# Config wiring
# ===========================================================================

class TestConfig(unittest.TestCase):

    def test_config_resolves_real_calibration(self):
        cfg, path = load_ft_config()
        cal = load_calibration(cfg, path)
        self.assertEqual(cal.serial, "FT29831")
        self.assertEqual(cal.source_path, REAL_CAL.resolve())

    def test_from_config_builds_without_hardware(self):
        ft = FTInterface.from_config()
        self.assertEqual(ft.device, "Dev1")
        self.assertEqual(ft.sample_rate_hz, 2000.0)
        self.assertEqual(len(ft.channels), NUM_GAUGES)
        self.assertFalse(ft.connected)

    def test_config_declares_si_and_sensor_frame(self):
        cfg, _ = load_ft_config()
        self.assertEqual(cfg["output"]["force_unit"], "N")
        self.assertEqual(cfg["output"]["torque_unit"], "N_m")
        self.assertEqual(cfg["output"]["frame"], SENSOR_FRAME)

    def test_mapping_confirmed_by_measurement(self):
        # Task 9 confirmed the channel set by load response: only ai0..ai5 moved.
        cfg, _ = load_ft_config()
        self.assertTrue(cfg["daq"]["channel_mapping_confirmed"])

    def test_channel_health_is_tracked_separately_from_mapping(self):
        # Knowing which channel a gauge is on says nothing about whether that
        # channel carries a signal, so the two stay separate fields. Both are
        # now good, and any fault that reappears must be recorded here rather
        # than left implicit.
        cfg, _ = load_ft_config()
        self.assertIn("all_channels_healthy", cfg["daq"])
        # Both are now good, after SG5 was relocated to the AI6 pair. They stay
        # separate fields regardless: a confirmed mapping says nothing about
        # whether every mapped channel is actually driven, and collapsing the
        # two is what let a dead SG5 produce authoritative-looking forces.
        self.assertTrue(cfg["daq"]["channel_mapping_confirmed"])
        self.assertTrue(cfg["daq"]["all_channels_healthy"])
        # Faults may exist without contradicting all_channels_healthy, as long
        # as none of them lands on a channel that is actually in use. That is
        # the invariant worth enforcing: a recorded fault must never sit under
        # an active gauge.
        faulty = {f["daq_channel"] for f in cfg["daq"]["known_hardware_faults"]}
        self.assertTrue(faulty.isdisjoint(set(cfg["daq"]["channels"])),
                        f"a known-faulty channel is assigned to a gauge: "
                        f"{faulty & set(cfg['daq']['channels'])}")

    def test_sg0_reference_is_terminal_34_not_35(self):
        """Guard the one wiring fact that caused every earlier symptom.

        Terminal 34 is AI0-, the differential partner of AI0+ on terminal 68.
        Terminal 35 is AI GND. Wiring SG0's reference to 35 leaves the AI0
        differential negative floating, which made Dev1/ai0 read as an open
        circuit and produced the phantom scale errors of Tasks 5-8.
        """
        cfg, _ = load_ft_config()
        sg0 = cfg["scb68a_wiring"]["gauges"]["SG0"]
        self.assertEqual(sg0["positive_terminal"], 68)
        self.assertEqual(sg0["negative_terminal"], 34)
        self.assertNotEqual(sg0["negative_terminal"], 35)

    def test_connector_is_recorded(self):
        # Which 68-pin connector the block is on shifts every channel by 16,
        # so it has to be part of the recorded configuration.
        cfg, _ = load_ft_config()
        self.assertEqual(cfg["daq"]["connector"], 0)
        self.assertEqual(cfg["scb68a_wiring"]["connector"], 0)

    def test_config_mapping_follows_scb68a_labels_with_a_connector_offset(self):
        """The mapping must be the label order, shifted by one connector.

        Terminals 68/65/33/30/28/60 are labelled AI0/AI2/AI1/AI3/AI4/AI5, so the
        gauge order SG0..SG5 is AI 0,2,1,3,4,5. Which physical channel that is
        depends on which 68-pin connector the SCB-68A is plugged into: connector
        0 gives ai0-ai15, connector 1 gives ai16-ai31. Assert the *pattern*, so
        this survives the block being moved again.
        """
        cfg, _ = load_ft_config()
        chans = cfg["daq"]["channels"]
        nums = [int(c.rsplit("ai", 1)[1]) for c in chans]
        base = nums[0]
        self.assertEqual(base, 16 * cfg["daq"]["connector"],
                         "channel base must match the recorded connector")
        self.assertIn(base, (0, 16), f"unexpected connector base channel {base}")
        # SG0..SG4 follow the SCB-68A label order 0,2,1,3,4. SG5 was moved off
        # terminal 60/26 onto the AI6 pair, so it is no longer at offset 5.
        self.assertEqual(nums[:5], [base + k for k in (0, 2, 1, 3, 4)])
        self.assertEqual(nums[5], base + 7, "SG5 is on the relocated AI7 pair")

    def test_known_bad_channels_are_never_assigned(self):
        """ai5 is open and ai6 couples 2.1% of its predecessor.

        Either one would silently corrupt forces rather than raise: a gauge
        with a small Fz coefficient can still dominate Fx, which is exactly how
        a dead SG5 went unnoticed for five tasks while Fz looked fine.
        """
        cfg, _ = load_ft_config()
        for bad in ("Dev1/ai5", "Dev1/ai6"):
            self.assertNotIn(bad, cfg["daq"]["channels"])

    def test_every_known_fault_is_documented(self):
        cfg, _ = load_ft_config()
        faults = cfg["daq"]["known_hardware_faults"]
        self.assertEqual({f["daq_channel"] for f in faults}, {"Dev1/ai5", "Dev1/ai6"})
        for f in faults:
            self.assertTrue(f.get("evidence"), f"{f['daq_channel']} lacks evidence")
            self.assertIn("path", f)
        # and the recorded wiring must still name the terminals it came from
        g = cfg["scb68a_wiring"]["gauges"]
        self.assertEqual([g[f"SG{i}"]["positive_terminal"] for i in range(6)],
                         [68, 65, 33, 30, 28, 60])

    def test_config_records_the_scb68a_wiring_provenance(self):
        # The mapping now rests on the SCB-68A silkscreen labels, so the
        # terminal-level wiring must stay recorded: it is the only evidence
        # tying a gauge to a channel, and it is not recoverable from software.
        cfg, _ = load_ft_config()
        gauges = cfg["scb68a_wiring"]["gauges"]
        self.assertEqual(sorted(gauges), [f"SG{i}" for i in range(6)])
        self.assertEqual(gauges["SG0"]["positive_terminal"], 68)
        self.assertEqual(gauges["SG2"]["positive_terminal"], 33)

    def test_validation_block_present(self):
        cfg, _ = load_ft_config()
        v = cfg["validation"]
        self.assertAlmostEqual(v["test_mass_kg"], 1.004)
        self.assertAlmostEqual(v["gravity_m_s2"], 9.80665)

    def test_empty_channels_is_an_error_not_a_default(self):
        import yaml
        cfg, path = load_ft_config()
        cfg["daq"]["channels"] = []
        tmp = Path(tempfile.mkdtemp()) / "ft_config.yaml"
        tmp.write_text(yaml.safe_dump(cfg))
        with self.assertRaises(ChannelMappingError):
            FTInterface.from_config(tmp)


class TestChannelOrderIntoCalibration(unittest.TestCase):
    """The voltage vector reaching the matrix must be [SG0..SG5], in order."""

    def test_synthetic_1_to_6_preserves_order(self):
        # SG0=1, SG1=2, ... SG5=6 must arrive at the converter in that order.
        cal = ATICalibration.from_file(REAL_CAL)
        v = np.array([1., 2., 3., 4., 5., 6.])
        # Column j of the matrix is the response to gauge j alone, so the
        # wrench must equal the column-weighted sum in exactly this order.
        expected = sum(v[j] * cal.si_matrix[:, j] for j in range(6))
        np.testing.assert_allclose(cal.to_wrench(v), expected, atol=1e-12)

    def test_each_gauge_hits_its_own_column(self):
        cal = ATICalibration.from_file(REAL_CAL)
        for j in range(6):
            unit = np.zeros(6); unit[j] = 1.0
            np.testing.assert_allclose(cal.to_wrench(unit), cal.si_matrix[:, j],
                                       atol=1e-12)

    def test_interface_channel_list_indexes_gauges_positionally(self):
        cfg, _ = load_ft_config()
        ft = FTInterface.from_config()
        self.assertEqual(ft.channels, cfg["daq"]["channels"])
        self.assertEqual(list(ft.gauge_map), ["SG0","SG1","SG2","SG3","SG4","SG5"])
        # raw row i must be gauge SGi
        for i, (sg, chan) in enumerate(ft.gauge_map.items()):
            self.assertEqual(sg, f"SG{i}")
            self.assertEqual(chan, ft.channels[i])

    def test_swapping_two_channels_changes_the_wrench(self):
        # Guards against an ordering bug silently producing plausible numbers.
        cal = ATICalibration.from_file(REAL_CAL)
        v = np.array([1., 2., 3., 4., 5., 6.])
        swapped = v[[1, 0, 2, 3, 4, 5]]
        self.assertGreater(np.max(np.abs(cal.to_wrench(v) - cal.to_wrench(swapped))), 1e-6)


class TestSeparationFromRobotFT(unittest.TestCase):

    def test_no_robot_ft_references(self):
        for name in ("ati_calibration.py", "ft_interface.py"):
            src = (PROJECT_ROOT / "src" / "vbts_platform" / name).read_text()
            body = src.split('"""', 2)[2] if src.count('"""') >= 2 else src
            for forbidden in ("fr5_io", "RealtimeState", "FT_GetForceTorque",
                              "FT_Guard", "FT_SetZero", "robot_ft"):
                self.assertNotIn(forbidden, body,
                                 f"{name} must not reference {forbidden}")

    def test_frame_is_sensor_frame(self):
        self.assertEqual(SENSOR_FRAME, "ATI_sensor_frame")


if __name__ == "__main__":
    unittest.main(verbosity=2)
