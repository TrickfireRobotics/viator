case $- in
*i*) ;;
*) return ;;
esac

# ---------- shell behavior ----------
export HISTCONTROL=ignoreboth:erasedups
export HISTSIZE=10000
export HISTFILESIZE=20000
shopt -s histappend checkwinsize

# ---------- colors ----------
if [ -x /usr/bin/dircolors ]; then
    test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    alias grep='grep --color=auto'
    alias fgrep='fgrep --color=auto'
    alias egrep='egrep --color=auto'
fi

# ---------- lesspipe ----------
[ -x /usr/bin/lesspipe ] && eval "$(SHELL=/bin/sh lesspipe)"

# ---------- ROS workspace overlay ----------
export ROS_WS="${ROS_WS:-/home/trickfire/urc-2023}"

_ros_source_env() {
    if [ -f "/opt/ros/${ROS_DISTRO}/setup.bash" ]; then
        source "/opt/ros/${ROS_DISTRO}/setup.bash"
    fi
    if [ -f "${ROS_WS}/install/setup.bash" ]; then
        source "${ROS_WS}/install/setup.bash"
    fi
}

if [ -z "${ROS_ENV_SOURCED:-}" ]; then
    _ros_source_env
    export ROS_ENV_SOURCED=1
fi

# ---------- prompt ----------
_tf_git_branch() {
    git symbolic-ref --quiet --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null
}

_tf_prompt() {
    local branch=""
    local reset="\[\e[0m\]"
    local pink="\[\e[38;2;233;60;171m\]"
    local green="\[\e[38;2;1;255;0m\]"
    local blue="\[\e[38;2;80;170;255m\]"

    branch="$(_tf_git_branch)"
    if [ -n "$branch" ]; then
        branch=" ${blue}(${branch})${reset}"
    fi

    PS1="${pink}\u${reset}:${green}\w${reset}${branch}\\$ "
}
PROMPT_COMMAND="_tf_prompt"

# ---------- aliases ----------
alias c='clear'
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

# ROS
alias rtl='ros2 topic list'
alias rte='ros2 topic echo'
alias rnl='ros2 node list'
alias rsl='ros2 service list'
alias rs='_ros_source_env'

# colcon
alias cb='colcon build --symlink-install --base-paths "$ROS_WS" --cmake-args -DCMAKE_BUILD_TYPE=Debug'

# ruff
alias rf='ruff check .'
alias rff='ruff check . --fix'
alias rfmt='ruff format .'

# ---------- helper functions ----------
ros-clean() {
    rm -rf "${ROS_WS}/build" "${ROS_WS}/install" "${ROS_WS}/log"
    echo "Cleaned build/install/log from ${ROS_WS}"
}

# ---------- bash completion ----------
if ! shopt -oq posix; then
    if [ -f /usr/share/bash-completion/bash_completion ]; then
        . /usr/share/bash-completion/bash_completion
    elif [ -f /etc/bash_completion ]; then
        . /etc/bash_completion
    fi
fi
