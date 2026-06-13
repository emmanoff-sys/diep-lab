#!/bin/bash

docker start diep-prometheus
docker start diep-grafana
docker start diep-node-exporter
docker start diep-cadvisor
docker start diep-mqtt
docker start diep-influxdb
docker start diep-nodered
docker start diep-smartmeter

docker ps
