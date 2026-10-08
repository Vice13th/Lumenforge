"""Measured-camera characterization infrastructure recovered from LumenParallel.

This module intentionally does not assert a measured camera IDT/profile. It exposes
fit/evaluation primitives and provenance receipts while leaving scientific gates open
until traceable measured data and independent reference measurements are available.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib
import json
import numpy as np

D65_XYZ = np.array([0.95047, 1.0, 1.08883], dtype=np.float64)


def _as_rgb(x):
    a = np.asarray(x, dtype=np.float64)
    if a.shape[-1] != 3 or not np.isfinite(a).all():
        raise ValueError("RGB input must be finite with final dimension 3")
    return a


def _as_xyz(x):
    a = np.asarray(x, dtype=np.float64)
    if a.shape[-1] != 3 or not np.isfinite(a).all():
        raise ValueError("XYZ input must be finite with final dimension 3")
    return a


def xyz_to_lab(xyz, white_xyz=D65_XYZ):
    x = _as_xyz(xyz); w = _as_xyz(white_xyz)
    if w.shape != (3,) or np.any(w <= 0):
        raise ValueError("white_xyz must be a positive 3-vector")
    r = x / w; delta = 6.0 / 29.0; d3 = delta ** 3
    f = np.where(r > d3, np.cbrt(np.maximum(r, 0.0)), r / (3 * delta**2) + 4.0 / 29.0)
    return np.stack([116.0*f[...,1]-16.0, 500.0*(f[...,0]-f[...,1]), 200.0*(f[...,1]-f[...,2])], axis=-1)


def ciede2000(lab1, lab2):
    a1 = _as_xyz(lab1); a2 = _as_xyz(lab2)
    if a1.shape != a2.shape: raise ValueError("lab1 and lab2 must have identical shapes")
    L1,A1,B1=np.moveaxis(a1,-1,0); L2,A2,B2=np.moveaxis(a2,-1,0)
    C1=np.hypot(A1,B1); C2=np.hypot(A2,B2); Cbar=(C1+C2)/2
    G=0.5*(1-np.sqrt((Cbar**7)/(Cbar**7+25**7))); ap1=(1+G)*A1; ap2=(1+G)*A2
    Cp1=np.hypot(ap1,B1); Cp2=np.hypot(ap2,B2); hp1=np.degrees(np.arctan2(B1,ap1))%360; hp2=np.degrees(np.arctan2(B2,ap2))%360
    dh=hp2-hp1; dh=np.where(dh>180,dh-360,dh); dh=np.where(dh<-180,dh+360,dh)
    dL=L2-L1; dC=Cp2-Cp1; dH=2*np.sqrt(np.maximum(Cp1*Cp2,0))*np.sin(np.radians(dh)/2)
    Lbar=(L1+L2)/2; Cbarp=(Cp1+Cp2)/2; hsum=hp1+hp2
    hbar=np.where(np.abs(hp1-hp2)<=180,hsum/2,np.where(hsum<360,(hsum+360)/2,(hsum-360)/2))
    T=1-.17*np.cos(np.radians(hbar-30))+.24*np.cos(np.radians(2*hbar))+.32*np.cos(np.radians(3*hbar+6))-.20*np.cos(np.radians(4*hbar-63))
    Sl=1+(0.015*(Lbar-50)**2)/np.sqrt(20+(Lbar-50)**2); Sc=1+.045*Cbarp; Sh=1+.015*Cbarp*T
    dtheta=30*np.exp(-((hbar-275)/25)**2); Rc=2*np.sqrt((Cbarp**7)/(Cbarp**7+25**7)); Rt=-Rc*np.sin(np.radians(2*dtheta))
    return np.sqrt((dL/Sl)**2+(dC/Sc)**2+(dH/Sh)**2+Rt*(dC/Sc)*(dH/Sh)).astype(np.float64)


def root_polynomial_degree2(rgb):
    x=_as_rgb(rgb)
    if np.min(x)<0: raise ValueError("root-polynomial input must be non-negative")
    r,g,b=np.moveaxis(x,-1,0)
    return np.stack([r,g,b,np.sqrt(r*g),np.sqrt(r*b),np.sqrt(g*b)],axis=-1)


def fit_rgb_to_xyz(rgb, xyz, ridge=0.0):
    x=_as_rgb(rgb).reshape(-1,3); y=_as_xyz(xyz).reshape(-1,3)
    if x.shape[0]!=y.shape[0] or x.shape[0]<3: raise ValueError("at least 3 paired RGB/XYZ samples are required")
    gram=x.T@x
    if ridge<0: raise ValueError("ridge must be >= 0")
    if ridge: gram += np.eye(3)*float(ridge)
    return np.linalg.solve(gram,x.T@y).astype(np.float64)


def fit_root_polynomial_degree2(rgb, xyz, ridge=0.0):
    x=root_polynomial_degree2(rgb).reshape(-1,6); y=_as_xyz(xyz).reshape(-1,3)
    if x.shape[0]!=y.shape[0] or x.shape[0]<6: raise ValueError("at least 6 paired RGB/XYZ samples are required")
    gram=x.T@x
    if ridge<0: raise ValueError("ridge must be >= 0")
    if ridge: gram += np.eye(6)*float(ridge)
    return np.linalg.solve(gram,x.T@y).astype(np.float64)


def predict_rgb_to_xyz(rgb,matrix): return np.einsum("...c,cd->...d",_as_rgb(rgb),np.asarray(matrix,np.float64),optimize=True)
def predict_root_polynomial_degree2(rgb,matrix): return np.einsum("...c,cd->...d",root_polynomial_degree2(rgb),np.asarray(matrix,np.float64),optimize=True)


def colorimetric_metrics(pred_xyz, ref_xyz, white_xyz=D65_XYZ):
    pred=_as_xyz(pred_xyz); ref=_as_xyz(ref_xyz)
    if pred.shape!=ref.shape: raise ValueError("pred_xyz and ref_xyz must have identical shapes")
    de=ciede2000(xyz_to_lab(pred,white_xyz),xyz_to_lab(ref,white_xyz)).reshape(-1)
    return {"count":int(de.size),"mean_delta_e00":float(np.mean(de)),"median_delta_e00":float(np.median(de)),"max_delta_e00":float(np.max(de)),"p95_delta_e00":float(np.percentile(de,95)),"min_delta_e00":float(np.min(de)),"all_finite":bool(np.isfinite(de).all())}


def held_out_indices(n,fraction=0.25):
    if n<4 or not 0.0<fraction<1.0: raise ValueError("invalid sample count or fraction")
    count=max(1,int(round(n*fraction))); return np.arange(n-count,n,dtype=int)

@dataclass(frozen=True)
class CameraFitReceipt:
    model:str
    train_count:int
    holdout_count:int
    matrix_sha256:str
    train_metrics:dict
    holdout_metrics:dict
    scientific_gate_status:str="infrastructure_only"
    def to_dict(self): return asdict(self)


def fit_and_evaluate(rgb,xyz,model="matrix3",holdout_indices_=None,ridge=0.0):
    x=_as_rgb(rgb).reshape(-1,3); y=_as_xyz(xyz).reshape(-1,3)
    if x.shape[0]!=y.shape[0]: raise ValueError("RGB/XYZ sample counts must match")
    hold=held_out_indices(x.shape[0]) if holdout_indices_ is None else np.asarray(holdout_indices_,dtype=int)
    if hold.ndim!=1 or np.any(hold<0) or np.any(hold>=x.shape[0]): raise ValueError("invalid holdout indices")
    mask=np.ones(x.shape[0],dtype=bool); mask[hold]=False
    if model=="matrix3": matrix=fit_rgb_to_xyz(x[mask],y[mask],ridge); predict=predict_rgb_to_xyz
    elif model=="root_poly2": matrix=fit_root_polynomial_degree2(x[mask],y[mask],ridge); predict=predict_root_polynomial_degree2
    else: raise ValueError("model must be matrix3 or root_poly2")
    train_pred=predict(x[mask],matrix); hold_pred=predict(x[hold],matrix)
    digest=hashlib.sha256(np.ascontiguousarray(matrix).tobytes()).hexdigest()
    return CameraFitReceipt(model,int(mask.sum()),int(hold.size),digest,colorimetric_metrics(train_pred,y[mask]),colorimetric_metrics(hold_pred,y[hold]))


def receipt_json(receipt): return json.dumps(receipt.to_dict(),sort_keys=True,indent=2)
