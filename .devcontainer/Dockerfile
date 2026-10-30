# Ubuntu 22.04 with ROS 2 Humble
FROM ros:humble-ros-base-jammy AS base

# ---- system packages ----
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install --no-install-recommends -y \
    python3-pip \
    python3.10-venv \
    ros-humble-rosbridge-server \
    ros-humble-rosapi \
    usbutils \
    can-utils \
    iproute2 \
    kmod \
    # cv_bridge
    python3-numpy \
    libboost-python-dev \
    libopencv-dev \
    python3-opencv \
    ros-humble-cv-bridge

RUN echo "/opt/ros/$ROS_DISTRO/lib" > /etc/ld.so.conf.d/ros2.conf \
    && echo "/opt/ros/$ROS_DISTRO/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH)" >> /etc/ld.so.conf.d/ros2.conf \
    && ldconfig

RUN pip3 install --no-cache-dir \
    "numpy<2" \
    moteus \
    pyusb \
    pybind11 \
    pybind11-stubgen

# ---- myactuator_rmd for RMD-X8 motors ----

    # https://github.com/2b-t/myactuator_rmd/commit/c43980cac5948cfd4974a96b86fbac0a80749ed6
ARG MYACTUATOR_RMD_SHA=c43980cac5948cfd4974a96b86fbac0a80749ed6

RUN git clone https://github.com/2b-t/myactuator_rmd.git /tmp/myactuator_rmd \
    && git -C /tmp/myactuator_rmd checkout "$MYACTUATOR_RMD_SHA" \
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

# non-sudo permissions to run can control related commands
COPY .devcontainer/trickfire-can.sudoers /etc/sudoers.d/trickfire-can
RUN chmod 0440 /etc/sudoers.d/trickfire-can && visudo -cf /etc/sudoers.d/trickfire-can

# ---- dev ----
FROM base AS dev

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install --no-install-recommends -y \
    ssh-client \
    && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y nodejs

RUN pip3 install --no-cache-dir \
    ruff \
    mypy \
    && curl -sSL "https://github.com/mvdan/sh/releases/download/v3.10.0/shfmt_v3.10.0_linux_$(dpkg --print-architecture)" \
    -o /usr/local/bin/shfmt \
    && chmod +x /usr/local/bin/shfmt

COPY .devcontainer/trickfire.bashrc /home/trickfire/.bashrc

ENV VIATOR_CONTAINER=dev

USER trickfire
