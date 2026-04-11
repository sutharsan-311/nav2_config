# Installation

## Prerequisites

You need a working ROS2 installation (Humble or Jazzy) with Nav2. If Nav2 isn't installed yet:

```bash
sudo apt install ros-$ROS_DISTRO-nav2-bringup
```

nav2_config also needs PyQt6. Here's where it gets slightly annoying: `python3-pyqt6` is only packaged for Ubuntu 24.04 (Jazzy). On Humble (22.04), you install it via pip instead.

**Humble (22.04):**
```bash
pip install PyQt6
```

**Jazzy (24.04):**
```bash
sudo apt install python3-pyqt6
```

The `rosdep install` command below handles this automatically — it knows which distro you're on and picks the right method.

## Install from Source

```bash
# Clone into your workspace
cd ~/ros2_ws/src
git clone https://github.com/sutharsan-311/nav2_config.git

# Install all ROS dependencies (handles PyQt6 for your distro automatically)
cd ~/ros2_ws
rosdep install --from-paths src --ignore-src -r -y

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

**python3-pyqt6 not found on 22.04**

`rosdep install` may skip `python3-pyqt6` on Humble because it's not in the 22.04 apt repos. The fallback is `pip install PyQt6`. This is a known packaging gap — the package.xml conditionally depends on `python3-pyqt6` for Jazzy and falls back to the pip package on older distros, but rosdep doesn't always handle that correctly.

**ImportError: libGL.so.1 on headless systems**

PyQt6 needs OpenGL. On headless CI or Docker environments:

```bash
sudo apt install libgl1
```

**colcon build fails with CMake errors**

nav2_config is a pure Python package — it shouldn't need CMake at all. If you're seeing CMake errors, something else in your workspace is interfering. Try building with `--packages-select nav2_config` to isolate.
