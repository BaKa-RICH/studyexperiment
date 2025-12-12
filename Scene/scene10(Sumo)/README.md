1.	Roadrunner导出filmbox地图，carla导入地图make Import(没有Carla可以省略这步)

2.	用netconvert将.xodr文件生成.net.xml文件
netconvert --opendrive SuzhouNorthStation.xodr -o test.net.xml

3.	用netedit打开.net.xml文件，查看道路id

4.	根据编号，编写.rou.xml文件，定义route, vehicle, flow… ，
参考  https://sumo.dlr.de/docs/Definition_of_Vehicles%2C_Vehicle_Types%2C_and_Routes.html

5.	写.sumocfg文件，修改.rou.xml和.net.xml路径，修改config.py中的sumo_cfg_file路径, 运行Scene10_sumo v2.py看效果

6.	修改车辆驾驶行为参数vType，添加控制逻辑，再运行Scene10_sumo v2.py看效果

7.	收集碰撞数据，运行collect_accident_data.py

8.	回放碰撞, 修改变量vehicle_trace ，collisions_trace和collisions_number，运行replay_accident.py。


#### 更正：
1. 地图修改：原地图中草坪位置有些偏移，地图已替换放在压缩包中
2. bug修复：新建一个回放专用的文件夹，删掉所有的车流（flow，vehicle）定义，因为如果定义了从0时刻就生产的车辆，那么初始化联合仿真会立马生产这些车，导致replay_accident.py中生成事故周围车辆失败
,别忘了修改config.py中的sumocfg路径
3. bug修复：要等发生事故的车生成完毕，再开始视角跟踪，否则会报错


#### TODO: 
有时创建车辆出错：Invalid departlane definition for vehicle "xxx"

traci.vehicle.add暂时不支持在十字路口生成车辆