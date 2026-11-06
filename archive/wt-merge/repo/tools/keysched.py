#!/usr/bin/env python3
"""Key-injection schedules for the QwenOS keyboard mailbox (the Python twin of rv32_fast's -K).

Schedule file, one key per line, in order (blank lines and # comments ignored):
    shell_ready <key>     inject when the guest is parked in KEY_WAIT (pc == qos_key_park): one key per park,
                          i.e. exactly like a person typing at the prompt
    frame <N> <key>       inject once N frame markers (console byte 0x02) have been printed
    <instr> <key>         inject once <instr> guest instructions have retired
<key> is one character, or: \\n \\r \\b \\e space enter backspace esc 0xNN

INJECTION PROTOCOL (what a pause/resume driver such as the Qwen chunk driver must do). Mailbox = RAM at
symbol qos_input_mailbox (0x154): u32 seq at +0, u8 q[4] at +4.  To push key K while the guest is paused
(between chunks / at a breakpoint), in this order:
    1. write byte K to address 0x158 + (seq & 3)         (seq = current value of the u32 at 0x154)
    2. write u32 (seq + 1) to address 0x154              (publish LAST)
Pause points:  `shell_ready`: the pc of kernel symbol qos_key_park (readelf: 0x40030 in kernel-live.elf), which is a
single `ret`; stop BEFORE executing it (a ROM breakpoint there), push one key, resume at that pc.  The guest then
polls once more, echoes, and parks again: ~100 instructions per typed key.  `frame N`: the chunk that prints the
Nth 0x02 byte ends; push then.  `<instr>`: push after exactly that many retired instructions.
Never push more than 4 keys between guest polls (the guest drops the oldest) - rv32_fast pushes at most 4 per boundary.
"""
import re,sys
from pathlib import Path

KEYS={'\\n':10,'enter':10,'\\r':13,'\\b':8,'backspace':8,'\\e':27,'esc':27,'space':32}
def key(tok):
    if tok in KEYS:return KEYS[tok]
    if tok.startswith('0x'):return int(tok,16)
    if len(tok)==1:return ord(tok)
    raise ValueError('bad key %r'%tok)

def parse(text):
    out=[]
    for ln in text.splitlines():
        t=ln.split('#')[0].split()
        if not t:continue
        if t[0]=='shell_ready' and len(t)==2:out.append(('park',0,key(t[1])))
        elif t[0]=='frame' and len(t)==3:out.append(('frame',int(t[1]),key(t[2])))
        elif t[0].isdigit() and len(t)==2:out.append(('instr',int(t[0]),key(t[1])))
        else:raise ValueError('bad schedule line %r'%ln)
    return out

def type_lines(text,trigger='shell_ready'):
    """schedule text that types `text` at the shell prompt ('\\n' = Enter)"""
    names={' ':'space','\n':'\\n'}
    return ''.join('%s %s\n'%(trigger,names.get(c,c)) for c in text)

class Driver:
    """Runs a python reference CPU (rv32_qwenputer.CPU) with a schedule.  `park_pc` is qos_key_park."""
    def __init__(self,cpu,kbox,park_pc,sched):
        self.cpu,self.kbox,self.park,self.sched,self.i=cpu,kbox,park_pc,list(sched),0
        self.frames=0;self.nout=0;self.log=[]
    def push(self,k,why):
        c=self.cpu;seq=c.load(self.kbox,4)
        c.store(self.kbox+4+(seq&3),1,k);c.store(self.kbox,4,seq+1)   # data first, seq LAST
        self.log.append((c.steps,k,why));self.i+=1
    def run(self,limit,stop=None):
        c=self.cpu
        for _ in range(limit):
            if c.halted or (stop and stop(self)):break
            if c.pc==self.park:
                if self.i<len(self.sched) and self.sched[self.i][0]!='frame':self.push(self.sched[self.i][2],'park')
                else:break   # idle: nothing to type
            elif self.i<len(self.sched) and self.sched[self.i][0]=='instr' and c.steps>=self.sched[self.i][1]:
                self.push(self.sched[self.i][2],'instr')
            c.step()
            if len(c.byte_events)!=self.nout:
                for b in c.byte_events[self.nout:]:
                    if b==2:
                        self.frames+=1
                        n=0
                        while self.i<len(self.sched) and self.sched[self.i][0]=='frame' and self.frames>=self.sched[self.i][1] and n<4:
                            self.push(self.sched[self.i][2],'frame');n+=1
                self.nout=len(c.byte_events)
        return ''.join(c.output)
if __name__=='__main__':
    for e in parse(Path(sys.argv[1]).read_text()):print(e)
