#!/usr/bin/env python3

'''
* requires:
pip install --user libtmux psutil

* add to .tmux.conf:
set-hook -g after-new-window "rename-window 'win#{window_id}'"

* add to .zshrc:
save_last_tmux_pane_cmd () { [ "$TMUX_PANE" = "" ] && return; local d=/tmp/tmux-pane-cmds; mkdir -p $d; echo "$1" > $d/$TMUX_PANE; }
preexec_functions+=(save_last_tmux_pane_cmd)
'''

import sys
import os
import datetime
import time
from optparse import OptionParser

import yaml
import libtmux
import psutil

parser = OptionParser()
parser.add_option("-x", "--execute", dest="execute_commands", default=False, help='auto-execute previously running commands in panes', action='store_true')
parser.add_option("-d", "--delay", dest="delay", default=0.0, help='delay between creating panes (in seconds)', type='float')
(opts, args) = parser.parse_args()

if not args:
    print('usage:')
    print('tumuxum.py save FILENAME SESSION')
    print('tumuxum.py load FILENAME SESSION')

elif args[0] == 'save':
    fn, sessname = args[1:3]

    server = libtmux.Server()
    session = server.find_where({'session_name': sessname})

    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    sessdir = os.environ['HOME']+f'/tmp/tmuxux/sessions/{sessname}/{ts}'
    os.makedirs(sessdir, exist_ok=True)

    def get_child(child, pane):
        r = {
            'status': child.status(),
            'cwd': child.cwd(),
            'cmdline': child.cmdline(),
        }

        if child.status() != 'stopped':
            if child.name() == 'vim':
                # pane.send_keys('C-z', enter=False, suppress_history=False)
                # pane.send_keys('fg', enter=True, suppress_history=False)
                pane.send_keys('C-c', enter=False, suppress_history=False)
                pane.send_keys(f':wall!', enter=True, suppress_history=False)
                sessfn = f'{sessdir}/session-{child.pid}.vim'
                pane.send_keys(f':mksession {sessfn}', enter=True, suppress_history=False, literal=True)
                r['vim_session'] = sessfn
                print(f'    * saving vim session ({child.pid}, at {child.cwd()}): {sessfn}')
            # elif any(s.split('/')[-1].startswith('ipython') for s in child.cmdline()[0:2]):
            #     pane.send_keys('C-c', enter=False, suppress_history=False)
            #     sessfn = f'{sessdir}/session-{child.pid}.pkl'
            #     pane.send_keys(f'import dill; dill.dump_session("{sessfn}")', enter=True, suppress_history=False, literal=True)
            #     r['dill_session'] = sessfn
            #     print(f'    * saving ipython session ({child.pid}, at {child.cwd()}): {sessfn}')
            else:
                print(f'    * saving command ({child.pid}, at {child.cwd()}): {r["cmdline"]}')

        return r

    def get_pane(p):
        scrollbackfn = f'{sessdir}/scrollback-{p.id}.txt'
        with open(scrollbackfn, 'w+') as f:
            f.write('\n'.join(s.rstrip() for s in p.cmd('capture-pane', '-p', '-J', '-S-').stdout))
        pd = {
            'active': bool(int(p.active)),
            'id': p.id,
            'scrollback': scrollbackfn,
        }
        if int(p.pid) != 0:
            proc = psutil.Process(int(p.pid))
            cmdfn = f'/tmp/tmux-pane-cmds/{p.id}'
            command = open(cmdfn).read().strip() if os.path.exists(cmdfn) else None
            if command and len([c for c in proc.children() if c.status() != 'stopped']) == 1 \
                and not command.startswith('vim ') \
                and not any(c for c in proc.children() if c.status() != 'stopped' and c.name() == 'vim'):
                pd.update({
                    'command': command,
                    'cwd': p.current_path,
                })
                print(f'  * saving pane at {pd["cwd"]}: {pd["command"]}')
            else:
                pd.update({
                    'cwd': proc.cwd(),
                    'cmdline': proc.cmdline(),
                })
                pd.update({
                    'children': {c.pid: get_child(c, p) for c in proc.children()},
                })
                print(f'  * saving pane at {proc.cwd()}: {pd["cmdline"]}')
        else:
            print(f'  * saving pane: EMPTY')
            pd.update({
                'cwd': None,
                'cmdline': [],
                'children': {},
            })
        return pd

    def get_window(w):
        print(f'* saving window: {w.name}')
        return {
            'id': w.id,
            'index': int(w.index),
            'name': w.name,
            'layout': w.layout,
            'active': bool(int(w.active)),
            'panes': [
                get_pane(p) for p in w.panes
                if p.id != os.environ.get('TMUX_PANE')],
        }

    d = {
        'session_name': sessname,
        'windows': [get_window(w) for w in session.list_windows()],
    }
    with open(fn, 'w+') as f: yaml.dump(d, f)

elif args[0] == 'load':
    fn, sessname = args[1:3]
    if len(args) == 2:
        fn = args[1]
        sessname = None
    else:
        fn, sessname = args[1:3]

    d = yaml.load(open(fn), Loader=yaml.FullLoader)
    if not sessname: sessname = d['session_name']

    server = libtmux.Server()
    session = server.find_where({'session_name': sessname})
    if not session:
        session = server.new_session(sessname)
        updating = False
    else:
        updating = True

    def load_pane(pane, pd):
        if 'scrollback' in pd:
            pane.send_keys(f' cat {pd["scrollback"]}', enter=False, suppress_history=False, literal=True)
            pane.clear()
            pane.send_keys(f'', enter=True, suppress_history=False, literal=True)

        def handle_cmd(cmd):
            pane.send_keys(cmd, enter=opts.execute_commands, suppress_history=False, literal=True)
            print('   ', 'executed:' if opts.execute_commands else 'typed:', cmd)

        if 'command' in pd:
            pane.send_keys(f' cd {pd["cwd"]}', enter=True, suppress_history=False, literal=True)
            handle_cmd(pd['command'])
        else:
            for cd in pd['children'].values():
                if cd['status'] != 'stopped':
                    pane.send_keys(f' cd {cd["cwd"]}', enter=True, suppress_history=False, literal=True)
                    cmd = " ".join(cd["cmdline"])
                    if 'vim_session' in cd:
                        pane.send_keys(f' vim -S {cd["vim_session"]}', enter=True, suppress_history=False, literal=True)
                        print(f'    * loading vim session: {cd["vim_session"]}')
                    elif 'dill_session' in cd:
                        pane.send_keys(cmd, enter=True, suppress_history=False, literal=True)
                        pane.send_keys(f' import dill; dill.load_session({cd["dill_session"]!r})', enter=True, suppress_history=False, literal=True)
                        print(f'    * loading ipython session: {cd["dill_session"]}')
                    else:
                        handle_cmd(cmd)
                    break

    def load_window(wd):
        w = session.new_window(wd['name'], attach=False) # window_index=...
        p = w.panes[0]
        for pd in wd['panes']:
            print(f'  * creating pane: {pd.get("command") or pd["cmdline"]}')
            p = p.split_window()
            load_pane(p, pd)
            if pd['active']:
                active_pane = p
            time.sleep(opts.delay)
        w.panes[0].cmd('kill-pane')
        w.select_layout(wd['layout'])
        active_pane.select_pane()
        return w

    active_win = None
    for wd in d['windows']:
        if session.find_where({'window_name': wd['name']}):
            print(f'already exists window {wd["name"]}')
            continue
        print(f'* creating window: {wd["name"]}')
        w = load_window(wd)
        if wd['active']:
            active_win = w

    if active_win:
        active_win.select_window()
    if not updating:
        session.windows[0].kill_window()

