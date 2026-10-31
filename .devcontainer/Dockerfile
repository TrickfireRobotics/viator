# Ubuntu 22.04 with ROS 2 Humble
FROM ros:humble-ros-base-jammy AS base

# ---- system packages ----
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install --no-install-recommends -y \
    python3-pip \
    python3.10-venv \
    usbutils \
    can-utils \
    iproute2 \
    kmod \
    libboost-python-dev \
    libopencv-dev

RUN echo "/opt/ros/$ROS_DISTRO/lib" > /etc/ld.so.conf.d/ros2.conf \
    && echo "/opt/ros/$ROS_DISTRO/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH)" >> /etc/ld.so.conf.d/ros2.conf \
    && ldconfig

# ---- python dependencies ----
RUN pip3 install --no-cache-dir \
    numpy \
    moteus \
    pyusb \
    pybind11 \
    pybind11-stubgen

# ---- ROS dependencies, from the package.xml manifests ----
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=bind,source=src,target=/tmp/ws/src \
    rosdep init 2>/dev/null || true; \
    rosdep update --rosdistro "$ROS_DISTRO" \
    && DEBIAN_FRONTEND=noninteractive apt-get update \
    && rosdep install --from-paths /tmp/ws/src --ignore-src -y --rosdistro "$ROS_DISTRO"

# ---- myactuator_rmd for RMD-X8 motors ----
RUN git clone https://github.com/2b-t/myactuator_rmd.git /tmp/myactuator_rmd \
    && cmake -S /tmp/myactuator_rmd -B /tmp/myactuator_rmd/build -D PYTHON_BINDINGS=on \
    && cmake --build /tmp/myactuator_rmd/build -j "$(nproc)" \
    && cmake --install /tmp/myactuator_rmd/build \
    && ldconfig \
    && pip3 install --no-cache-dir /tmp/myactuator_rmd \
    && pybind11-stubgen myactuator_rmd_py -o /usr/local/lib/python3.10/dist-packages \
    && rm -rf /tmp/myactuator_rmd

# ---- user ----
RUN useradd trickfire --shell /bin/bash --create-home --no-log-init -G video,sudo,dialout,plugdev \
    && touch /home/trickfire/.sudo_as_admin_successful \
    && chown trickfire:trickfire /home/trickfire/.sudo_as_admin_successful

# non-sudo permissions to run can control related commands
COPY .devcontainer/trickfire-can.sudoers /etc/sudoers.d/trickfire-can
RUN chmod 0440 /etc/sudoers.d/trickfire-can && visudo -cf /etc/sudoers.d/trickfire-can

COPY .devcontainer/trickfire.bashrc /home/trickfire/.bashrc
RUN chown trickfire:trickfire /home/trickfire/.bashrc

# ---- rover ----
FROM base AS rover
ENV VIATOR_CONTAINER=rover
USER trickfire

# ---- dev ----
FROM base AS dev

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install --no-install-recommends -y \
    ssh-client \
    && curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y nodejs

RUN pip3 install --no-cache-dir \
    ruff \
    mypy

ENV VIATOR_CONTAINER=dev

USER trickfire
