# Using nav2_config with a Remote Robot

nav2_config runs on your laptop. Nav2 runs on the robot. This is the normal setup for field testing — you don't want a GUI application eating CPU on the robot's compute.

ROS2 handles the communication, but you need to make sure both machines can find each other on the network.

## Setup Overview

```
Laptop                          Robot
──────────────────────          ──────────────────────
nav2_config (GUI)               Nav2 stack running
rclpy discovers nodes    ←───   /controller_server
reads/writes params             /planner_server
                                /amcl
                                etc.
```

## Step 1: Match ROS_DOMAIN_ID

Both machines must use the same domain ID. The default is 0. If your network has multiple robots or teams, you may already be using a custom ID.

Check what's set on the robot:
```bash
echo $ROS_DOMAIN_ID
```

Set the same value on your laptop before launching nav2_config:
```bash
export ROS_DOMAIN_ID=42   # match whatever the robot uses
```

Put this in your `~/.bashrc` if you always work with this robot.

## Step 2: DDS Discovery

ROS2 uses DDS for communication. Which DDS middleware you're using matters for cross-machine discovery.

**Check which middleware is active:**
```bash
echo $RMW_IMPLEMENTATION
```

**CycloneDDS** (common default on Jazzy):

CycloneDDS does multicast discovery by default. This works well on simple networks. On networks that block multicast, you'll need peer configuration:

```xml
<!-- ~/cyclone_dds.xml -->
<CycloneDDS>
  <Domain>
    <Discovery>
      <Peers>
        <Peer Address="192.168.1.50"/>  <!-- robot IP -->
      </Peers>
    </Discovery>
  </Domain>
</CycloneDDS>
```

```bash
export CYCLONEDDS_URI=file:///home/$USER/cyclone_dds.xml
```

**FastDDS** (default on Humble):

FastDDS uses multicast by default too. For networks that block it, create a unicast profile:

```xml
<!-- ~/fastdds_profile.xml -->
<?xml version="1.0" encoding="UTF-8" ?>
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
  <transport_descriptors>
    <transport_descriptor>
      <transport_id>udp_transport</transport_id>
      <type>UDPv4</type>
    </transport_descriptor>
  </transport_descriptors>
  <participant profile_name="default_profile" is_default_profile="true">
    <rtps>
      <userTransports>
        <transport_id>udp_transport</transport_id>
      </userTransports>
      <builtin>
        <metatrafficUnicastLocatorList>
          <locator>
            <udpv4>
              <address>192.168.1.50</address>  <!-- robot IP -->
            </udpv4>
          </locator>
        </metatrafficUnicastLocatorList>
      </builtin>
    </rtps>
  </participant>
</profiles>
```

```bash
export FASTRTPS_DEFAULT_PROFILES_FILE=~/fastdds_profile.xml
```

## Step 3: Network Requirements

nav2_config calls ROS2 parameter services, which use DDS. DDS needs UDP traffic to flow freely between the two machines.

- Both machines should be on the **same subnet** (e.g. 192.168.1.x). Routing DDS across subnets is possible but requires explicit peer configuration and is more fragile.
- If you're using a firewall on either machine, DDS needs UDP ports open. The exact ports depend on the DDS implementation, but a practical approach during development is to allow all UDP between the two hosts:

```bash
# On the robot (allow UDP from laptop IP)
sudo ufw allow from 192.168.1.100 proto udp  # replace with laptop IP
```

## Step 4: Source the Same ROS Environment

Your laptop needs the same ROS2 packages sourced as the robot. If the robot runs Jazzy but your laptop has Humble sourced, you'll get protocol mismatches.

```bash
source /opt/ros/jazzy/setup.bash  # match robot's ROS distro
source ~/ros2_ws/install/setup.bash
```

## Step 5: Sync the Config File

nav2_config needs a copy of the robot's nav2_params.yaml locally — it uses this as the source of truth for parameter values and writes changes back to it.

Copy it from the robot:
```bash
scp robot@192.168.1.50:~/nav2_ws/src/robot_bringup/config/nav2_params.yaml ~/nav2_params.yaml
```

Or mount the robot's filesystem via SSHFS if you want changes to reflect on the robot immediately:
```bash
sshfs robot@192.168.1.50:/home/robot ~/robot_fs
```

## Step 6: Verify the Connection

Before launching nav2_config, confirm your laptop can see the robot's nodes:

```bash
ros2 node list
```

You should see the robot's Nav2 nodes listed. If you see nothing, the DDS discovery isn't working — go back to Step 2.

If you can see the nodes, try calling a service directly:
```bash
ros2 service call /controller_server/list_parameters rcl_interfaces/srv/ListParameters
```

## Launch

```bash
ros2 run nav2_config gui
```

Then File > Load Config → select your local copy of nav2_params.yaml.

nav2_config will discover the robot's nodes automatically. The left panel shows each node with a green dot when it responds to service calls. If a node shows gray even though `ros2 node list` shows it, there's a service timeout issue — likely network latency. See [troubleshooting.md](troubleshooting.md).
