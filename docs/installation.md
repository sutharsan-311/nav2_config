# Installation

## Prerequisites

You need a working ROS2 installation (Humble or Jazzy) with Nav2. If Nav2 isn't installed yet:

```bash
sudo apt install ros-$ROS_DISTRO-nav2-bringup
```

nav2_config also needs PyQt6, and how you get it depends on your distro:

**Jazzy (24.04):** `python3-pyqt6` is an apt package, and there's a rosdep key for it ([ros/rosdistro#50683](https://github.com/ros/rosdistro/pull/50683)), so the `rosdep install` step below installs it for you — nothing manual needed.

**Humble (22.04):** PyQt6 isn't in the 22.04 apt repos, so the rosdep key resolves to nothing on Jammy. Thanks to that same key, `rosdep install` no longer errors on `python3-pyqt6` — it recognizes it and skips cleanly — but it won't install PyQt6 either, so install it once via pip:

```bash
pip install PyQt6
```

## Install from Source

```bash
# Clone into your workspace
cd ~/ros2_ws/src
git clone https://github.com/sutharsan-311/nav2_config.git

# Install ROS dependencies (installs PyQt6 automatically on Jazzy)
cd ~/ros2_ws
rosdep install --from-paths src --ignore-src -r -y

# On Humble (22.04) only: PyQt6 isn't in apt, so install it via pip
pip install PyQt6

# Build
colcon build --packages-select nav2_config

# Source
source install/setup.bash
```

## Verify

```bash
ros2 run nav2_config gui --help
```

You should see the nav2_config launch options. If you get a `ModuleNotFoundError` for PyQt6, the rosdep step didn't fully resolve — run the pip fallback manually:

```bash
pip install PyQt6
```

Then rebuild:

```bash
colcon build --packages-select nav2_config && source install/setup.bash
```

## Known Issues

**python3-pyqt6 not installed on Humble (22.04)**

PyQt6 isn't packaged for Ubuntu 22.04, so on Humble the `python3-pyqt6` rosdep key resolves to null. `rosdep install` recognizes the key and skips it cleanly — it no longer errors out the way it did before [ros/rosdistro#50683](https://github.com/ros/rosdistro/pull/50683) added the key — but it won't install PyQt6 for you. Install it once via pip:

```bash
pip install PyQt6
```

On Jazzy (24.04) this is fully automatic — `python3-pyqt6` is a real apt package and rosdep installs it.

**ImportError: libGL.so.1 on headless systems**

PyQt6 needs OpenGL. On headless CI or Docker environments:

```bash
sudo apt install libgl1
```

**colcon build fails with CMake errors**

nav2_config is a pure Python package — it shouldn't need CMake at all. If you're seeing CMake errors, something else in your workspace is interfering. Try building with `--packages-select nav2_config` to isolate.
