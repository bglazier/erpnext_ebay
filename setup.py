# -*- coding: utf-8 -*-
from setuptools import setup, find_packages
import re, ast

version = '0.0.1'

with open('requirements.txt') as f:
	install_requires = f.read().strip().split('\n')

setup(
	name='erpnext_ebay',
	version=version,
	description='Ebay Integration',
	author='Ben Glazier',
	author_email='ben@benjaminglazier.com',
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
	#dependency_links=[str(ir._link) for ir in requirements if ir._link]
)
