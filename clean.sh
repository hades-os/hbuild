#!/bin/bash

dirs=("sources" "builds" "system_prefix" "system_files" "tools" "packages" "works" "logs")

for dir in ${dirs[@]}; do
  rm -fr ${dir}
  mkdir -pv ${dir}
done

cp "build_files/cross_file.txt" "sources/cross_file.txt"

podman kill --all
podman rm -f --all