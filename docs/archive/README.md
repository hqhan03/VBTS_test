# 보관된 문서

지워진 게 아니라 대체된 것들이다. 어떤 판단이 어떤 근거로 내려졌는지 추적할
때만 보면 된다. **현재 상태를 알고 싶으면 `docs/` 로 돌아갈 것.**

| 파일 | 시점 | 무엇으로 대체되었나 |
|---|---|---|
| `ft_robot_frame_integration.md` | 08-26 | `frames_and_transforms.md`. "아직 변환이 없다, 만들려면 무엇이 필요한가"를 적은 문서. 부호 규약과 "이 리그는 통상적인 경우가 아니다" 절은 새 문서로 옮겼다 |
| `robot_ft_integration_status.md` | 08-26 | `frames_and_transforms.md`. "F/T는 끝, 로봇은 아직 연결 못 함, 호스트 네트워크가 막고 있음" — 전부 해결됨 |
| `sensor_base_transform.md` | 08-31 | `frames_and_transforms.md` 로 통합. 내용은 여전히 유효하며 새 문서의 본문이 되었다 |
| `HANDOFF.md` | 08-31 | `docs/README.md`. 하드웨어 상세는 `config/` 가, TCP 이력은 `tcp_calibration_history.md` 가, 절차는 `measurement_protocol.md` 가 가져갔다 |
| `HANDOFF_20260826.md.bak` | 08-26 | 위 문서의 더 오래된 백업 |
| `campaign_protocol.html` | 09-05 | `campaign_protocol.md` 의 렌더본. 원본이 바뀌어 낡았다 |

**주의: 여기 있는 수치를 그대로 쓰지 말 것.** 특히
`ft_robot_frame_integration.md` 는 변환이 존재하지 않는다고 말하는데, 지금은
있다. `HANDOFF.md` 의 "세 개의 게이트"는 캠페인이 실제로 쓰지 않는 코드 경로를
설명한다 — 실제 안전장치는 `docs/README.md` 에 있다.
