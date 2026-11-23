"""Fixed poppler invocation, with inherited resource and network restrictions."""
import os,sys,resource
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from worker_guard import isolate
resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(10,11));resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2));resource.setrlimit(resource.RLIMIT_FSIZE,(12*1024**2,12*1024**2));resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))
program=sys.argv[1];page=sys.argv[4]
if program!='/usr/bin/pdftoppm' or not page.isdigit() or not 1<=int(page)<=250:raise ValueError('Invalid fixed renderer arguments')
isolate(deny_exec=False)
os.execve(program,[program,'-f',page,'-l',page,'-scale-to','2000','-singlefile','-png',sys.argv[2],sys.argv[3]],{'LANG':'C.UTF-8','OMP_THREAD_LIMIT':'1'})
