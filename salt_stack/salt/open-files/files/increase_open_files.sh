#!/usr/bin/env bash

echo -e "fs.file-max=500000" | sudo tee --append /etc/sysctl.conf
echo -e "root\t\tsoft\tnofile\t500000" | sudo tee --append /etc/security/limits.conf
echo -e "root\t\thard\tnofile\t500000" | sudo tee --append /etc/security/limits.conf
echo -e "*\t\tsoft\tnofile\t500000" | sudo tee --append /etc/security/limits.conf
echo -e "*\t\thard\tnofile\t500000" | sudo tee --append /etc/security/limits.conf
