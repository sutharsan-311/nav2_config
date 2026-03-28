from setuptools import setup, find_packages
import os
from glob import glob

package_name = 'nav2_config'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Install schema files
        (os.path.join('share', package_name, 'schema'), glob('nav2_config/schema/*.json')),
# Install desktop entry for Linux app launchers
        (os.path.join('share', 'applications'), ['resource/nav2_config.desktop']),
    ],
    install_requires=[
        'setuptools',
        'PyYAML',
        'PyQt6',
    ],
    zip_safe=True,
    maintainer='Sutharsan',
    maintainer_email='sutharsanmail311@gmail.com',
    description='Real-time visual parameter tuning GUI for Nav2',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'gui = nav2_config.main:main',
        ],
    },
)
