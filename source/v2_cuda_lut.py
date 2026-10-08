"""Optional CUDA tetrahedral LUT backend recovered from LumenParallel."""
import numpy as np

_KERNEL = None


def available():
    try:
        import cupy as cp
        return cp.cuda.runtime.getDeviceCount() > 0
    except Exception:
        return False


def device_info():
    try:
        import cupy as cp
        d = cp.cuda.Device()
        props = cp.cuda.runtime.getDeviceProperties(d.id)
        name = props["name"]
        if isinstance(name, bytes):
            name = name.decode(errors="replace")
        return {
            "available": True,
            "device": str(name),
            "device_id": int(d.id),
            "runtime": cp.runtime.runtimeGetVersion(),
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def _kernel():
    global _KERNEL
    if _KERNEL is not None:
        return _KERNEL
    import cupy as cp
    src = r'''
    extern "C" __global__ void tetra_lut(const float* x, const float* t, float* y, int n, int total, float d0,float d1,float d2,float m0,float m1,float m2) {
        int p = blockDim.x * blockIdx.x + threadIdx.x;
        if (p >= total) return;
        float r = x[p*3+0], g = x[p*3+1], b = x[p*3+2];
        r = fminf(fmaxf((r-d0)/(m0-d0),0.0f),1.0f); g = fminf(fmaxf((g-d1)/(m1-d1),0.0f),1.0f); b = fminf(fmaxf((b-d2)/(m2-d2),0.0f),1.0f);
        float pr=r*(n-1), pg=g*(n-1), pb=b*(n-1);
        int ir=(int)floorf(pr), ig=(int)floorf(pg), ib=(int)floorf(pb);
        float fr=pr-ir, fg=pg-ig, fb=pb-ib;
        ir=min(ir,n-2); ig=min(ig,n-2); ib=min(ib,n-2);
        int base=((ir*n+ig)*n+ib)*3;
        int c100=base+n*n*3, c010=base+n*3, c001=base+3;
        int c110=c100+n*3, c101=c100+3, c011=c010+3, c111=c110+3;
        for(int c=0;c<3;c++){
            float v000=t[base+c], v100=t[c100+c], v010=t[c010+c], v001=t[c001+c];
            float v110=t[c110+c], v101=t[c101+c], v011=t[c011+c], v111=t[c111+c], v;
            if(fr>=fg && fg>=fb) v=v000+fr*(v100-v000)+fg*(v110-v100)+fb*(v111-v110);
            else if(fr>=fb && fb>=fg) v=v000+fr*(v100-v000)+fb*(v101-v100)+fg*(v111-v101);
            else if(fg>=fr && fr>=fb) v=v000+fg*(v010-v000)+fr*(v110-v010)+fb*(v111-v110);
            else if(fg>=fb && fb>=fr) v=v000+fg*(v010-v000)+fb*(v011-v010)+fr*(v111-v011);
            else if(fb>=fr && fr>=fg) v=v000+fb*(v001-v000)+fr*(v101-v001)+fg*(v111-v101);
            else v=v000+fb*(v001-v000)+fg*(v011-v001)+fr*(v111-v011);
            y[p*3+c]=v;
        }
    }
    '''
    _KERNEL = cp.RawKernel(src, 'tetra_lut')
    return _KERNEL


def tetrahedral_cuda(rgb, lut3d):
    import cupy as cp
    x = np.asarray(rgb, np.float32)
    shape = x.shape
    tbl, dmin, dmax = lut3d
    if x.ndim < 2 or x.shape[-1] != 3:
        raise ValueError("RGB input must have last dimension 3")
    if tbl.ndim != 4 or tbl.shape[-1] != 3 or tbl.shape[0] < 2 or tbl.shape[1] != tbl.shape[0] or tbl.shape[2] != tbl.shape[0]:
        raise ValueError("invalid 3D LUT")
    dx = cp.asarray(np.ascontiguousarray(x.reshape(-1, 3)))
    dt = cp.asarray(np.ascontiguousarray(tbl.reshape(-1, 3)))
    total = dx.shape[0]
    out = cp.empty_like(dx)
    dm = np.asarray(dmin, np.float32)
    dxm = np.asarray(dmax, np.float32)
    if dm.shape != (3,) or dxm.shape != (3,):
        raise ValueError("LUT domain bounds must be RGB triples")
    k = _kernel()
    threads = 256
    blocks = (total + threads - 1) // threads
    args = (dx, dt, out, np.int32(tbl.shape[0]), np.int32(total),
            np.float32(dm[0]), np.float32(dm[1]), np.float32(dm[2]),
            np.float32(dxm[0]), np.float32(dxm[1]), np.float32(dxm[2]))
    k((blocks,), (threads,), args)
    cp.cuda.Stream.null.synchronize()
    return cp.asnumpy(out).reshape(shape)
