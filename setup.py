from setuptools import setup

setup(
    name='ranger',
    version='0.1.0',
    author='Assi Maimon',
    author_email='maimon33@gmail.com',
    py_modules=['ranger'],
    description='Control your AWS instances',
    entry_points={
        'console_scripts': [
                'ranger = ranger:ranger',
        ],
    },
    install_requires=[
        'click==6.7',
        'boto3',
        'wryte==0.1.1',
        'psutil==5.6.6',
        'prettytable',
        'python-crontab==2.2.8',
    ]
)
