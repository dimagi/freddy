try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name='freddy',
    version='1.0-dev',
    description='Facility Registry API wrapper',
    author='Mike White',
    author_email='mwhite@dimagi.com',
    url='http://github.com/dimagi/freddy',
    packages=['freddy'],
    license='MIT',
    install_requires=[
        'python-dateutil>=1.5',
        'requests==1.1.0',  # 1.0 is probably fine
        'pytz'
    ]
)
