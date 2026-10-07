# Three stages:
#
#   base     everything the rover needs to run, and nothing else
#   dev      base plus the toolchain, this is what the devcontainer uses
#   runtime  base plus a Release build of the workspace baked in
#
# The point of the split is that `runtime` is a deployment artifact. It carries its own
# compiled workspace, so nothing is cloned, pip installed or compiled on the Orin at
# deploy time, and the image that gets tested is byte-for-byte the image that drives.

# Pinning the full tag rather than `ros:humble` so the Ubuntu release is explicit. To pin
# harder, resolve a digest with
#   docker buildx imagetools inspect ros:humble-ros-base-jammy
# and replace this with `ros@sha256:...`.
FROM ros:humble-ros-base-jammy AS base

# ---- runtime system packages ----
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install --no-install-recommends -y \
    python3-pip \
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

# textual is pinned to the major the dashboard was written against; the rest are
# constrained where a new major would plausibly break us.
RUN pip3 install --no-cache-dir \
    "numpy<2" \
    moteus \
    "textual>=8,<9" \
    pyusb \
    pybind11 \
    pybind11-stubgen

# ---- myactuator_rmd (RMD-X8 motor driver) ----
# Pinned by commit rather than cloned from the branch tip: an upstream change used to be
# able to alter the rover's motor driver with no corresponding change in this repo.
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

# trickfire is non-root, but SocketCAN raw sockets (candump/cansend and the RMD-X8
# node's CanDriver) need CAP_NET_RAW/CAP_NET_ADMIN, which a non-root exec doesn't get
# just from the container's `cap_add`/`privileged` settings. Grant NOPASSWD sudo for
# only the specific CAN tooling and the built can_rmdx8 node so this works without an
# interactive password, without handing trickfire unrestricted root.
COPY .devcontainer/trickfire-can.sudoers /etc/sudoers.d/trickfire-can
RUN chmod 0440 /etc/sudoers.d/trickfire-can && visudo -cf /etc/sudoers.d/trickfire-can

# ---------------------------------------------------------------------------
# dev: the devcontainer. Source comes in over a bind mount, nothing is baked in.
# ---------------------------------------------------------------------------
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
    pre-commit \
    "pydocstyle>=6.3.0" \
    && curl -sSL "https://github.com/mvdan/sh/releases/download/v3.10.0/shfmt_v3.10.0_linux_$(dpkg --print-architecture)" \
    -o /usr/local/bin/shfmt \
    && chmod +x /usr/local/bin/shfmt

COPY .devcontainer/trickfire.bashrc /home/trickfire/.bashrc

USER trickfire

# ---------------------------------------------------------------------------
# runtime: the deployment artifact. Workspace is compiled in, no bind mount.
# ---------------------------------------------------------------------------
FROM base AS runtime

WORKDIR /opt/viator

COPY src/ /opt/viator/src/

# --merge-install for one flat tree, and no --symlink-install: symlinks would point back
# at a source tree that doesn't exist on the rover. Release rather than the Debug the dev
# build uses, because this one actually drives.
RUN . "/opt/ros/$ROS_DISTRO/setup.sh" \
    && colcon build \
    --merge-install \
    --base-paths . \
    --cmake-args -DCMAKE_BUILD_TYPE=Release \
    && rm -rf build log \
    && chown -R trickfire:trickfire /opt/viator

COPY deploy/entrypoint.sh /usr/local/bin/viator-entrypoint
RUN chmod +x /usr/local/bin/viator-entrypoint

USER trickfire

ENTRYPOINT ["/usr/local/bin/viator-entrypoint"]
CMD ["launch"]
