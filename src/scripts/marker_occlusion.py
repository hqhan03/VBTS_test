"""Where did the ball land relative to the dot lattice, and how much of the
contact is hidden under an opaque dot?"""
import re, yaml, numpy as np, pandas as pd, cv2
from pathlib import Path
from scipy import ndimage
ROOT=Path("/home/nrel/Desktop/KDC-tactile-testing-platform")
DS=ROOT/"data/20260911_VBTSresolution_dataset/DIGIT_Marker/20260908_passB_ball8"
can=yaml.safe_load((DS/"CANONICAL.yaml").read_text())["canonical"]
geo=pd.read_csv(ROOT/"data/analysis/marker_geometry.csv").set_index("unit")
rows=[]
for unit,info in can.items():
    run=DS/info["run"]
    fr=pd.read_csv(run/"stream"/"frames.csv")
    ref=cv2.imread(str(run/"reference_collect.png"))
    refg=cv2.cvtColor(ref,cv2.COLOR_BGR2GRAY).astype(np.float32)
    # dots on the reference
    hp=cv2.GaussianBlur(refg,(0,0),25)-refg
    thr=hp>max(4.0,np.percentile(hp,99.0)*0.35)
    lab,n=ndimage.label(thr); areas=ndimage.sum(thr,lab,range(1,n+1))
    keep=[i+1 for i,a in enumerate(areas) if 1500<=a<=60000]
    dots=np.array(ndimage.center_of_mass(thr,lab,keep))[:,::-1] if keep else np.zeros((0,2))
    dotmask=np.isin(lab,keep)
    # imprint: the deepest normal frame
    nb=fr[fr.segment.str.startswith("normal")] if "segment" in fr else fr
    fz=nb.get("Fz_s_corr",nb.get("Fz_s")).astype(float)
    row=nb.loc[fz.abs().idxmax()]
    img=cv2.imread(str(run/"stream"/row.file),cv2.IMREAD_GRAYSCALE).astype(np.float32)
    diff=np.abs(img-refg)
    diff=cv2.GaussianBlur(diff,(0,0),9)
    diff[dotmask]=0                                   # the dots' own change is not the imprint
    yx=np.unravel_index(np.argmax(diff),diff.shape)
    cy,cx=float(yx[0]),float(yx[1])
    g=geo.loc[unit]
    # **격자 축척**으로 낸 접촉 크기를 쓴다. 옛 열(contact_d_px)은 회귀 축척으로
    # 계산돼 접촉 원을 20 % 작게 그렸다 (cross_principle.md 3.5b).
    a_px=(g.contact_d_px_grid if "contact_d_px_grid" in g.index else g.contact_d_px)/2
    yy,xx=np.mgrid[0:refg.shape[0],0:refg.shape[1]]
    incontact=(yy-cy)**2+(xx-cx)**2<=a_px**2
    covered=float((dotmask&incontact).sum()/max(incontact.sum(),1))
    dist=float(np.hypot(dots[:,0]-cx,dots[:,1]-cy).min()) if len(dots) else np.nan
    rows.append(dict(unit=unit,short=unit.replace("DIGIT_Marker_",""),cx=round(cx),cy=round(cy),
                     n_dots=len(dots),contact_r_px=round(a_px,1),pitch_px=round(g.pitch_px,1),
                     dot_dist_px=round(dist,1),phase=round(dist/g.pitch_px,3),
                     covered_frac=round(covered,3),max_fz=round(float(abs(row.get("Fz_s_corr",row.get("Fz_s")))),2)))
    print(f"  {unit:30s} 접촉중심({cx:4.0f},{cy:4.0f}) 최근접점 {dist:5.0f} px  위상 {dist/g.pitch_px:.2f}  가려진 비율 {covered*100:4.1f} %",flush=True)
pd.DataFrame(rows).to_csv(ROOT/"data/analysis/marker_occlusion.csv",index=False)
print("  -> data/analysis/marker_occlusion.csv")
