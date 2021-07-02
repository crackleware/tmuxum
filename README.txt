Usage: tmuxumt.py [options] (save|load)

Options:
  -h, --help            show this help message and exit
  -s SESSION, --session=SESSION
                        name of the session to save (default is active
                        session)
  -f FILE, --file=FILE  load session from/save session to FILE
  -t DIR, --sessions-directory=DIR
                        write session related files under DIR
  -x, --execute         auto-execute previously running commands in panes
  -d DELAY, --delay=DELAY
                        delay between creating panes (in seconds)

TmuxumT session manager saves and loads:

- window names and order
- layout of panes in windows
- active command which is running in pane
- last executed command in pane
- current directory for pane
- entire scrollback for pane
- vim session for pane using :mksession command

Only missing windows are loaded.

* add to .tmux.conf:
set-hook -g after-new-window "rename-window 'win#{window_id}'"

* add to .zshrc:
setopt HIST_IGNORE_SPACE
save_last_tmux_pane_cmd () { [ "$TMUX_PANE" = "" ] && return; local d=/tmp/tmux-pane-cmds; mkdir -p $d; echo "$1" > $d/$TMUX_PANE; }
preexec_functions+=(save_last_tmux_pane_cmd)