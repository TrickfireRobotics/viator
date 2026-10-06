# Ubuntu 22.04 with ROS 2 Humble
FROM ros:humble AS viator

# ---- system packages ----
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install --no-install-recommends -y \
    git \
    python3-pip \
    ssh-client \
    ros-humble-rosbridge-server \
    usbutils \
    can-utils \
    iproute2 \
    kmod \
    # cv_bridge
    python3-numpy \
    libboost-python-dev \
    libopencv-dev \
    python3-opencv

RUN pip3 install --no-cache-dir \
    moteus \
    pyusb \
    pybind11 \
    pybind11-stubgen \
    "pydocstyle>=6.3.0"

# ---- dev tooling ----

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y nodejs

RUN pip3 install --no-cache-dir ruff mypy pre-commit \
    && curl -sSL "https://github.com/mvdan/sh/releases/download/v3.10.0/shfmt_v3.10.0_linux_$(dpkg --print-architecture)" \
    -o /usr/local/bin/shfmt \
    && chmod +x /usr/local/bin/shfmt

# ---- myactuator_rmd (RMD-X8 motor driver) ----

RUN git clone --depth 1 https://github.com/2b-t/myactuator_rmd.git /tmp/myactuator_rmd \
    && cmake -S /tmp/myactuator_rmd -B /tmp/myactuator_rmd/build -D PYTHON_BINDINGS=on \
    && cmake --build /tmp/myactuator_rmd/build -j "$(nproc)" \
    && cmake --install /tmp/myactuator_rmd/build \
    && ldconfig \
    && pip3 install /tmp/myactuator_rmd \
    && pybind11-stubgen myactuator_rmd_py -o /usr/local/lib/python3.10/dist-packages \
    && rm -rf /tmp/myactuator_rmd

# ---- user ----
RUN useradd trickfire --shell /bin/bash --create-home --no-log-init -G video,sudo,dialout,plugdev \
    && echo "trickfire:trickfire" | chpasswd \
    && touch /home/trickfire/.sudo_as_admin_successful \
    && chown trickfire:trickfire /home/trickfire/.sudo_as_admin_successful

# trickfire is non-root, but SocketCAN raw sockets (candump/cansend and the RMD-X8
# node's CanDriver) need CAP_NET_RAW/CAP_NET_ADMIN, which a non-root exec doesn't get
# just from the container's `cap_add`/`privileged` settings. Grant NOPASSWD sudo for
# only the specific CAN tooling and the built can_rmdx8 node so this works without an
# interactive password, without handing trickfire unrestricted root.
COPY .devcontainer/trickfire-can-sudoers /etc/sudoers.d/trickfire-can
RUN chmod 0440 /etc/sudoers.d/trickfire-can && visudo -cf /etc/sudoers.d/trickfire-can

COPY .devcontainer/trickfire.bashrc /home/trickfire/.bashrc

USER trickfire
