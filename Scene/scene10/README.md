1.	Roadrunner导出filmbox地图，carla导入地图make Import

2.	用netconvert将.xodr文件生成.net.xml文件
netconvert --opendrive SuzhouNorthStation.xodr -o test.net.xml

3.	用netedit打开.net.xml文件，查看道路id

4.	根据编号，编写.rou.xml文件，定义route, vehicle, flow… ，
参考  https://sumo.dlr.de/docs/Definition_of_Vehicles%2C_Vehicle_Types%2C_and_Routes.html

5.	写.sumocfg文件，修改.rou.xml和.net.xml路径，修改config.py中的sumo_cfg_file路径, 运行Scene10_sumo v2.py看效果

6.	修改车辆驾驶行为参数vType，添加控制逻辑，再运行Scene10_sumo v2.py看效果

7.	收集碰撞数据，运行collect_accident_data.py

8.	回放碰撞, 修改变量vehicle_trace ，collisions_trace和collisions_number，运行replay_accident.py。
