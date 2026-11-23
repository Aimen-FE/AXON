"""Linux isolation applied only to short-lived AXON workers."""
import ctypes,ctypes.util

def isolate(deny_exec=True):
    lib=ctypes.CDLL(ctypes.util.find_library('seccomp') or 'libseccomp.so.2')
    lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
    lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
    lib.seccomp_rule_add.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint]
    lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_release.argtypes=[ctypes.c_void_p]
    ctx=lib.seccomp_init(0x7fff0000)
    if not ctx:raise ValueError('No isolation')
    try:
        names=['socket','connect','fork','vfork','ptrace']+(['execve','execveat'] if deny_exec else [])
        for name in names:
            number=lib.seccomp_syscall_resolve_name(name.encode())
            if number>=0 and lib.seccomp_rule_add(ctx,0x00050000|1,number,0)!=0:raise ValueError('Isolation failed')
        if lib.seccomp_load(ctx)!=0:raise ValueError('Isolation failed')
    finally:lib.seccomp_release(ctx)
