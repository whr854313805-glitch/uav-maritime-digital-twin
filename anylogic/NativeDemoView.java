package maritime;

import com.anylogic.engine.*;
import com.anylogic.engine.presentation.*;
import com.google.gson.*;
import java.awt.Color;
import java.awt.Font;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;

/** Presentation only: reads the existing workbench clock/XY; never plans in Z. */
public final class NativeDemoView {
 final NativeWorkbench h; final ShapeGroup scene,map2,screen,overlay; final ShapeWindow3D window;final Camera3D viewCamera;
 final ShapeText title,clock,stats,story,legend,speedLabel; final ShapeSlider timeline,speedSlider;
 final ShapePolyLine route3,straight3,rangeLink3,route2,straight2,rangeLink2,uavDirection3,uavDirection2,shipDirection3,shipDirection2;
 final ShapeGroup drone3,drone2; final ShapeOval shadow,start3,end3,start2,end2;final ShapeText startLabel,endLabel;
 final ArrayList<Ship> ships=new ArrayList<>(); final ArrayList<ShapePolyLine> buildings=new ArrayList<>();
 final ShapePolyLine groundRoute,verticalLink,buildingLink3,buildingLink2,buildingBox3,buildingBox2;
 final ShapePolyLine referenceTrack3,referenceTrack2;
 final ShapeOval ghost3,ghost2,levelRing;final ShapeText detail;
 boolean follow=false,compare=true;double buildingDistance=Double.NaN,directDistance=Double.NaN;double[] boundary=null;int nearestBuilding=-1;double lastBuildingX=Double.NaN,lastBuildingY=Double.NaN;
 final JsonObject support,study;JsonObject result;String lastIdentity="";boolean demo=true,threeD=true,initial=false,setting=false,focusWhenReady=false,refreshPending=false;
 final NativeScenery scenery;boolean harborView=false;
 double cameraTrackedX=Double.NaN,cameraTrackedY=Double.NaN;
 double cx,cy,extent=700,t0,t1,closest=Double.NaN;int ticks=0,buildingCount=0;String error="",lastGeometry="";
 final Color PURPLE=new Color(145,64,224),WATER=new Color(146,195,215),GRAY=new Color(133,147,158),NAVY=new Color(24,44,66),CYAN=new Color(22,140,143);
 final Font heading=new Font("Microsoft YaHei",Font.BOLD,25),body=new Font("Microsoft YaHei",0,17);
 static final ShapeDrawMode D3=ShapeDrawMode.SHAPE_DRAW_3D;
 public static void attach(Agent a,String root,String py)throws Exception{try{NativeDemoView view=new NativeDemoView(new NativeWorkbench(a,root,py));view.startViewControls();}catch(Throwable e){try(java.io.PrintWriter w=new java.io.PrintWriter(Paths.get(root,"anylogic/visual_demo/startup_error.txt").toFile(),"UTF-8")){e.printStackTrace(w);}throw new RuntimeException(e);}}
 NativeDemoView(NativeWorkbench host)throws Exception{
  h=host;support=h.json(h.root.resolve("anylogic/visual_demo/support.json"));study=h.json(h.root.resolve("output/research_points/study/study.json"));
  if(!NativeWorkbench.str(support,"raw_sha256").equals(NativeWorkbench.str(h.workspace.getAsJsonObject("source"),"raw_sha256")))throw new IllegalStateException("3D显示与AIS来源不一致");
  // Keep the original presentation out of the 3D scene; no original source is edited.
  scene=new ShapeGroup(h.owner,D3,true,0,0,0,0);h.p.add(scene);
  map2=new ShapeGroup(h.owner,ShapeDrawMode.SHAPE_DRAW_2D,true,0,0,0,0);h.p.add(map2);
  screen=new ShapeGroup(h.owner,ShapeDrawMode.SHAPE_DRAW_2D,true,0,0,0,0);h.p.add(screen);
  overlay=new ShapeGroup(h.owner,ShapeDrawMode.SHAPE_DRAW_2D,true,0,0,0,0);h.p.add(overlay);
  box(screen,0,0,1680,235,Color.WHITE);box(screen,1050,0,630,1060,Color.WHITE);box(screen,0,900,1680,160,Color.WHITE);
  title=text(screen,30,18,"维港无人机 · 历史AIS避让演示",heading,NAVY);
  text(screen,30,58,"官方OMPL SST规划；直线合格时直接飞；蓝线为固定AIS船舶轨迹。",body,NAVY);
  button(screen,30,104,130,"演示播放/暂停",()->{if(!h.busy&&h.packet!=null&&h.packet.has("trajectory")&&!h.packet.get("trajectory").isJsonNull()){h.playing=!h.playing;}});
  button(screen,175,104,120,"回到出发",()->{h.now=t0;h.playing=false;h.draw();sync();});
  button(screen,310,104,160,"跳到最近船距",()->{if(Double.isFinite(closest)){h.now=closest;h.playing=false;h.draw();sync();}});
  button(screen,485,104,100,"二维视图",()->set3D(false));button(screen,600,104,100,"三维视图",()->set3D(true));
  button(screen,715,104,125,"重置相机",()->{boolean changed=harborView;harborView=false;if(changed)updateBuildings(true);camera();});
  speedLabel=text(screen,855,82,"播放速度：1倍",body,NAVY);
  speedSlider=new ShapeSlider(h.owner,true,855,108,155,28,NAVY,false,1,10,ShapeControl.TYPE_INT){@Override public void action(){if(!setting){setValue(value,false);h.speed=Math.max(1,Math.min(10,Math.round(value)));h.draw();sync();}}};speedSlider.setStep(1,false);screen.add(speedSlider);
  button(screen,30,154,155,"正常直飞",()->load("M2","固定任务"));
  button(screen,195,154,155,"同向绕行案例",()->load("encounter_M1_same_direction","遇船案例"));
  button(screen,360,154,155,"相向避让",()->load("encounter_M1_opposing","遇船案例"));
  button(screen,525,154,155,"起点拒绝案例",()->load("encounter_M1_start_conflict","遇船案例"));
  button(screen,690,154,155,"建筑避障",()->load("M4","固定任务"));
  button(screen,855,154,155,"孤立观测点",()->load("encounter_M1_singleton","遇船案例"));
  clock=text(screen,30,205,"正在读取历史记录…",body,NAVY);
  button(screen,30,185,235,"M1 尖沙咀—中环",()->load("M1","固定任务"));
  button(screen,280,185,235,"M2 北角—红磡",()->load("M2","固定任务"));
  button(screen,530,185,235,"M3 西湾河—三家村",()->load("M3","固定任务"));
  button(screen,780,185,235,"M4 尖沙咀/尖东—鲤鱼门",()->load("M4","固定任务"));
  clock.setPos(30,218);text(screen,730,218,"中键平移 · Ctrl＋滚轮缩放",body,NAVY);
  text(screen,1080,28,"当前线路与任务",heading,NAVY);
  text(screen,1080,79,"紫色：无人机与已规划路线\n灰色：起终点之间的直线对照\n蓝色船：实测位置；橙色船：加工插值\n绿点：起点；红点：终点",body,NAVY);
  stats=text(screen,1080,245,"",body,NAVY);story=text(screen,1080,440,"",body,NAVY);
  legend=text(screen,1080,755,"浅灰细线：路线投影；紫点：当前落点\n蓝色细线：参考船固定AIS片段，不随无人机改道\n红点：假如直飞的对照，非另一架飞机\n青线/90米圈：水平距离，非空间斜距\n金线：原建筑包络距离，仍按二维检查\n楼高来自官方快照；未知高度40米为示意\n岸线为官方概化背景；不参与路径计算\n历史回放非预测；90米是模型中心距",body,NAVY);
  detail=text(screen,1080,680,"",body,NAVY);
  button(screen,30,873,160,"全景 / 跟随特写",()->{harborView=false;follow=!follow;camera();updateBuildings(true);refreshPending=true;});
  button(screen,205,873,160,"直飞对照 开/关",()->{compare=!compare;sync();});
  button(screen,380,873,160,"跳到最近建筑",()->{JsonObject checks=support.getAsJsonObject("building_checks");if(checks.has(h.runId)){h.now=NativeWorkbench.num(checks.getAsJsonObject(h.runId),"closest_capture_s");h.playing=false;h.draw();sync();}});
  button(screen,555,873,160,"跳到直飞冲突",()->{JsonObject checks=support.getAsJsonObject("ship_comparison_checks");if(checks.has(h.runId)){JsonObject c=checks.getAsJsonObject(h.runId);if(!c.get("direct_closest_capture_s").isJsonNull()){h.now=NativeWorkbench.num(c,"direct_closest_capture_s");h.playing=false;h.draw();sync();}}});button(screen,730,873,130,"维港全景",()->{harborView=true;follow=false;camera();updateBuildings(true);refreshPending=true;});text(screen,870,882,"拖动旋转",body,NAVY);
  text(screen,30,962,"任务时间轴（只覆盖本次飞行）：可拖动，也可跳到最近船距。",body,NAVY);
  text(screen,30,1005,"历史回放，不是未来船位预测。所有船距、路径和验收均按二维水平坐标计算。",body,NAVY);
  timeline=new ShapeSlider(h.owner,true,30,915,990,30,NAVY,false,0,1,ShapeControl.TYPE_DOUBLE){@Override public void action(){if(!setting){setValue(value,false);h.now=value;h.playing=false;h.draw();sync();}}};screen.add(timeline);
  button(overlay,1450,980,180,"演示 / 工作台",()->setDemo(!demo));
  // A real native WebGL 3D window, not a projected 2D image.
  java.lang.reflect.Field windowField=h.owner.getClass().getDeclaredField("demoWindow3D"),cameraField=h.owner.getClass().getDeclaredField("demoCamera3D");
  windowField.setAccessible(true);cameraField.setAccessible(true);
  window=(ShapeWindow3D)windowField.get(h.owner);viewCamera=(Camera3D)cameraField.get(h.owner);
  window.setNavigationMode(ShapeWindow3D.NAVIGATION_ROTATION_ONLY);window.setCamera(viewCamera,true);

  scenery=new NativeScenery(h,scene);
  route3=poly(scene,D3,PURPLE,null,0);straight3=poly(scene,D3,GRAY,null,0);rangeLink3=poly(scene,D3,CYAN,null,0);
  route3.setLineWidth(3);straight3.setLineWidth(1.5);rangeLink3.setLineWidth(2);
  route2=poly(map2,ShapeDrawMode.SHAPE_DRAW_2D,PURPLE,null,0);straight2=poly(map2,ShapeDrawMode.SHAPE_DRAW_2D,GRAY,null,0);straight2.setLineStyle(LineStyle.LINE_STYLE_DASHED);rangeLink2=poly(map2,ShapeDrawMode.SHAPE_DRAW_2D,CYAN,null,0);
  uavDirection3=poly(scene,D3,PURPLE,null,0);uavDirection2=poly(map2,ShapeDrawMode.SHAPE_DRAW_2D,PURPLE,null,0);shipDirection3=poly(scene,D3,h.blue,null,0);shipDirection2=poly(map2,ShapeDrawMode.SHAPE_DRAW_2D,h.blue,null,0);
  groundRoute=poly(scene,D3,new Color(185,193,200),null,0);groundRoute.setLineWidth(1);groundRoute.setLineStyle(LineStyle.LINE_STYLE_DASHED);verticalLink=poly(scene,D3,PURPLE,null,0);
  referenceTrack3=poly(scene,D3,h.blue,null,0);referenceTrack2=poly(map2,ShapeDrawMode.SHAPE_DRAW_2D,h.blue,null,0);referenceTrack3.setLineWidth(1);referenceTrack2.setLineWidth(1);
  buildingLink3=poly(scene,D3,new Color(195,125,0),null,0);buildingLink2=poly(map2,ShapeDrawMode.SHAPE_DRAW_2D,new Color(195,125,0),null,0);
  buildingBox3=poly(scene,D3,new Color(195,125,0),null,40);buildingBox2=poly(map2,ShapeDrawMode.SHAPE_DRAW_2D,new Color(195,125,0),null,0);
  ghost3=new ShapeOval(D3,true,0,0,1,0,Color.RED,Color.RED,4,4,2,2,LineStyle.LINE_STYLE_SOLID);scene.add(ghost3);
  ghost2=new ShapeOval(true,0,0,0,Color.RED,Color.RED,5,5,2,LineStyle.LINE_STYLE_SOLID);map2.add(ghost2);
  levelRing=new ShapeOval(D3,true,0,0,35,0,CYAN,null,90,90,0,2,LineStyle.LINE_STYLE_SOLID);scene.add(levelRing);
  drone3=drone(true);drone3.setScale(1.8);drone2=drone(false);scene.add(drone3);map2.add(drone2);
  shadow=new ShapeOval(D3,true,0,0,.4,0,PURPLE,PURPLE,3,3,.1,1,LineStyle.LINE_STYLE_SOLID);scene.add(shadow);
  start3=new ShapeOval(D3,true,0,0,.5,0,new Color(18,149,108),new Color(18,149,108),8,8,2,1,LineStyle.LINE_STYLE_SOLID);scene.add(start3);
  end3=new ShapeOval(D3,true,0,0,.5,0,new Color(213,68,83),new Color(213,68,83),8,8,2,1,LineStyle.LINE_STYLE_SOLID);scene.add(end3);
  start2=new ShapeOval(true,0,0,0,new Color(18,149,108),new Color(18,149,108),6,6,1,LineStyle.LINE_STYLE_SOLID);map2.add(start2);
  end2=new ShapeOval(true,0,0,0,new Color(213,68,83),new Color(213,68,83),6,6,1,LineStyle.LINE_STYLE_SOLID);map2.add(end2);
  startLabel=text(map2,0,0,"起点",body,NAVY);endLabel=text(map2,0,0,"终点",body,NAVY);
  for(JsonElement e:h.vessels)ships.add(new Ship(e.getAsJsonObject()));
  h.speed=1;h.playing=false;applyVisibility();pulse();
 }
 void startViewControls(){try{Path py=Paths.get(h.python),pyw=py.resolveSibling("pythonw.exe");new ProcessBuilder((Files.exists(pyw)?pyw:py).toString(),h.root.resolve("start_full_demo.py").toString(),"--controls-only",Long.toString(ProcessHandle.current().pid())).redirectErrorStream(true).redirectOutput(h.root.resolve("anylogic/visual_demo/controls_setup.log").toFile()).start();}catch(Exception e){error="View controls startup: "+e;}}
 String currentRouteId(){for(JsonElement e:study.getAsJsonArray("tasks")){String id=NativeWorkbench.str(e.getAsJsonObject(),"id");if(h.key.equals(id)||h.key.contains("_"+id+"_")||h.key.endsWith("_"+id))return id;}if(result!=null&&result.has("request")){JsonObject q=result.getAsJsonObject("request");for(JsonElement e:study.getAsJsonArray("tasks")){JsonObject task=e.getAsJsonObject();JsonArray gates=task.getAsJsonArray("gates");if(q.get("start").equals(gates.get(0).getAsJsonObject().get("point"))&&q.get("end").equals(gates.get(1).getAsJsonObject().get("point")))return NativeWorkbench.str(task,"id");}}return "未匹配固定线路";}
 String routeDescription(){String id=currentRouteId();switch(id){case "M1":return "M1 尖沙咀—中环";case "M2":return "M2 北角—红磡";case "M3":return "M3 西湾河—三家村";case "M4":return "M4 尖沙咀/尖东—鲤鱼门";default:return id;}}
 ShapeGroup[] hostGroups(){return new ShapeGroup[]{h.background,h.observations,h.interpolations,h.sites,h.routes,h.moving,h.aircraft,h.ui};}
 void box(ShapeGroup g,double x,double y,double w,double height,Color c){g.add(new ShapeRectangle(true,x,y,0,c,c,w,height,0,LineStyle.LINE_STYLE_SOLID));}
 ShapeText text(ShapeGroup g,double x,double y,String s,Font f,Color c){ShapeText t=new ShapeText(true,x,y,0,c,s,f,TextAlignment.ALIGNMENT_LEFT);g.add(t);return t;}
 ShapeButton button(ShapeGroup g,double x,double y,double w,String label,Runnable run){return h.button(g,x,y,w,label,run);}
 ShapePolyLine poly(ShapeGroup g,ShapeDrawMode mode,Color line,Color fill,double height){ShapePolyLine s=new ShapePolyLine(mode,true,0,0,0,line,fill,2,new double[]{0,0},new double[]{0,0},new double[]{0,0},fill!=null,height,2,LineStyle.LINE_STYLE_SOLID);g.add(s);return s;}
 void points(ShapePolyLine line,JsonArray ps,double z,boolean is3){line.setNPoints(ps.size());for(int i=0;i<ps.size();i++){double[] q=NativeWorkbench.xy(ps.get(i).getAsJsonArray());line.setPoint(i,is3?q[0]-cx:h.sx(q[0]),is3?cy-q[1]:h.sy(q[1]),is3?z:0);}}
 void pair(ShapePolyLine line,double[] a,double[] b,double z,boolean is3){JsonArray q=new JsonArray();for(double[] p:new double[][]{a,b}){JsonArray v=new JsonArray();v.add(p[0]);v.add(p[1]);q.add(v);}points(line,q,z,is3);}
 ShapeGroup drone(boolean three){ShapeGroup g=new ShapeGroup(h.owner,three?D3:ShapeDrawMode.SHAPE_DRAW_2D,true,0,0,0,0);double arm=three?18:22;for(double angle:new double[]{Math.PI/4,-Math.PI/4})g.add(new ShapeRectangle(three?D3:ShapeDrawMode.SHAPE_DRAW_2D,true,-arm/2,-1,0,angle,PURPLE,PURPLE,arm,2,three?1:0,1,LineStyle.LINE_STYLE_SOLID));for(int x:new int[]{-1,1})for(int y:new int[]{-1,1})g.add(new ShapeOval(three?D3:ShapeDrawMode.SHAPE_DRAW_2D,true,x*6,y*6,0,0,PURPLE,new Color(205,173,236),three?4:4,three?4:4,three?1:0,1,LineStyle.LINE_STYLE_SOLID));g.add(new ShapeRectangle(three?D3:ShapeDrawMode.SHAPE_DRAW_2D,true,-3,-3,1,0,PURPLE,PURPLE,6,6,three?3:0,1,LineStyle.LINE_STYLE_SOLID));return g;}
 final class Ship{
  final JsonObject vessel;final ShapeGroup mesh,icon;final ShapeOval ring3,ring2;final ArrayList<ShapePolyLine> hulls=new ArrayList<>();final ArrayList<ShapeRectangle> cabins=new ArrayList<>();Boolean directed=null;
  Ship(JsonObject v){vessel=v;mesh=new ShapeGroup(h.owner,D3,true,0,0,0,0);icon=new ShapeGroup(h.owner,ShapeDrawMode.SHAPE_DRAW_2D,true,0,0,0,0);mesh.setScale(1.3);scene.add(mesh);map2.add(icon);
   for(boolean d:new boolean[]{true,false}){ShapeGroup g=d?mesh:icon;ShapePolyLine hull=poly(g,d?D3:ShapeDrawMode.SHAPE_DRAW_2D,h.blue,h.blue,d?5:0);hull.setNPoints(6);hulls.add(hull);ShapeRectangle cabin=new ShapeRectangle(d?D3:ShapeDrawMode.SHAPE_DRAW_2D,true,-2,-1,d?6:0,0,Color.WHITE,Color.WHITE,4,7,d?4:0,1,LineStyle.LINE_STYLE_SOLID);cabins.add(cabin);g.add(cabin);}
   ring3=new ShapeOval(D3,true,0,0,.2,0,h.orange,null,90,90,0,1,LineStyle.LINE_STYLE_SOLID);scene.add(ring3);
   ring2=new ShapeOval(true,0,0,0,h.orange,null,90,90,1,LineStyle.LINE_STYLE_DASHED);map2.add(ring2);
  }
  void update(double t){double[] q=h.shipAt(vessel,t),v=shipDirection(vessel,t);boolean valid=demo&&q!=null&&h.inside(q);mesh.setVisible(valid&&threeD);icon.setVisible(valid&&!threeD);ring3.setVisible(valid&&threeD);ring2.setVisible(valid&&!threeD);if(!valid)return;
   boolean known=v!=null;if(directed==null||directed!=known){directed=known;double[] x={0,4.5,4.5,-4.5,-4.5,0},y={-12,-4,10,10,-4,-12};for(int j=0;j<hulls.size();j++)for(int i=0;i<6;i++)hulls.get(j).setPoint(i,known?x[i]:5*Math.cos(i*Math.PI/3),known?y[i]:5*Math.sin(i*Math.PI/3),j==0?1:0);for(ShapeRectangle cabin:cabins)cabin.setVisible(known);}
   double angle=known?Math.atan2(v[0],v[1]):0;mesh.setRotation(angle);icon.setRotation(angle);
   Color c=q[2]==1?h.blue:h.orange;for(ShapePolyLine hull:hulls){hull.setLineColor(c);hull.setFillColor(c);}mesh.setPos(q[0]-cx,cy-q[1]);icon.setPos(h.sx(q[0]),h.sy(q[1]));ring3.setPos(q[0]-cx,cy-q[1]);ring2.setPos(h.sx(q[0]),h.sy(q[1]));ring2.setRadius(90*h.scale);
  }
 }
 double[] shipDirection(JsonObject vessel,double t){for(JsonElement e:vessel.getAsJsonArray("segments")){JsonArray points=e.getAsJsonArray();for(int i=0;i+1<points.size();i++){JsonObject a=points.get(i).getAsJsonObject(),b=points.get(i+1).getAsJsonObject();double ta=NativeWorkbench.num(a,"t"),tb=NativeWorkbench.num(b,"t");if(tb>ta&&t>=ta&&t<=tb){double[] x=NativeWorkbench.xy(a.getAsJsonArray("xy")),y=NativeWorkbench.xy(b.getAsJsonArray("xy"));double dx=y[0]-x[0],dy=y[1]-x[1];if(Math.hypot(dx,dy)>1e-9)return new double[]{dx,dy};return null;}}}return null;}
 double[] droneDirection(){if(h.packet==null||!h.packet.has("trajectory")||h.packet.get("trajectory").isJsonNull())return null;JsonObject tr=h.packet.getAsJsonObject("trajectory");JsonArray times=tr.getAsJsonArray("times_s"),xy=tr.getAsJsonArray("xy");double local=h.now-t0+times.get(0).getAsDouble();for(int i=0;i+1<times.size();i++)if(local>=times.get(i).getAsDouble()&&local<=times.get(i+1).getAsDouble()){double[] a=NativeWorkbench.xy(xy.get(i).getAsJsonArray()),b=NativeWorkbench.xy(xy.get(i+1).getAsJsonArray());return new double[]{b[0]-a[0],b[1]-a[1]};}return null;}
 void arrow(ShapePolyLine shape,double[] p,double[] v,double length,double z,boolean is3){double n=Math.hypot(v[0],v[1]);if(n==0){shape.setVisible(false);return;}double x=v[0]/n,y=v[1]/n;double[][] offsets={{0,0},{x*length,y*length},{x*(length-9)-y*5,y*(length-9)+x*5},{x*length,y*length},{x*(length-9)+y*5,y*(length-9)-x*5}};JsonArray points=new JsonArray();for(double[] o:offsets){JsonArray q=new JsonArray();q.add(p[0]+o[0]);q.add(p[1]+o[1]);points.add(q);}points(shape,points,z,is3);}
 void load(String key,String category){if(h.busy)return;harborView=false;threeD=true;follow=key.equals("M4");h.speed=key.equals("M4")?10:1;focusWhenReady=true;h.category=category;h.categoryBox.setValue(category,false);h.taskBox.setItems(h.labels(),false);h.key=key;h.taskBox.setValue(NativeWorkbench.str(h.item(),"label"),false);h.updateDeparture();h.queue(false);}
 double focusTime(){JsonObject cases=support.getAsJsonObject("case_checks");if(cases.has(h.runId)){JsonObject c=cases.getAsJsonObject(h.runId);if(c.has("observation_time_s"))return c.get("observation_time_s").getAsDouble();}return t0;}
 String explanation(String direct){
  if(harborView)return "维港两岸 · 官方快照背景\n\nIFC 2 / IFC 1 / ICC / 中银大厦\n会展中心 / 尖沙咀钟楼\n\n楼高：官方顶高减基底高度。\n未知楼高40米为示意。\n岸线：地政总署概化快照。\n配色与屋顶装饰为表现样式。\n\n点‘重置相机’回到任务。";
  JsonObject registry=support.getAsJsonObject("demo_results");String kind=registry.has(h.runId)?NativeWorkbench.str(registry.getAsJsonObject(h.runId),"kind"):"other";
  if(kind.equals("straight"))return "正常直飞：没有必要绕路\n\n原M2路线只有起点和终点。\n沿直线通过已观测船舶检查；\n船距不冲突，就不增加绕行。\n\n点“回到出发”再播放。\n这不代表缺测船舶也已排除风险。";
  if(kind.equals("building"))return "建筑避障：直线受静态障碍限制\n\n灰线直飞；紫线是本次M4规划结果。\n金线量到最近的建筑包络边界。\n使用完整35335条建筑包络计算。\n\n默认10倍，拖动速度条选1—10倍。\n点‘跳到最近建筑’看最近处。\n切换‘全景 / 跟随特写’观察。\n楼高仅示意，不靠升高越过建筑。";
  if(kind.equals("singleton"))return "孤立观测：只检查真实存在的一刻\n\n切换时定位船477995429的观测时刻。\n蓝色为实测；前后未知，不补运动。\n可播放观察该孤立点消失；\n再点“孤立观测点”回到这一刻。\n\n与相向案例是同一次出发，\n不能算第二个独立遇船场景。";
  if(kind.equals("other"))return "当前工作台计算结果\n\n此运行未绑定固定演示分类。\n直线对照最小船距："+direct+"\n\n只显示本次真实计算结果，\n不套用其他案例的解释。";
  return (kind.equals("opposing")?"相向避让：参考船477995430\n原直线夹角约159°，并非严格正面对撞":"同向避让：直线飞行会离船太近")+"\n\n直飞全程最近："+direct+"；要求≥90米。\n紫线：官方SST＋实际飞行末段的结果。\n\n点‘跳到直飞冲突’看红点冲突；\n点‘跳到最近船距’检查绕行余量。\n\n船距按地面中心位置计算。\n这是历史回放，不是未来预测。";
 }
 void setDemo(boolean on){demo=on;h.playing=false;h.speed=on?1:10;if(!on){h.speedBox.setValue("10倍",false);h.staticLayers();}applyVisibility();sync();}
 void set3D(boolean on){threeD=on;applyVisibility();sync();refreshPending=true;}

 void applyVisibility(){screen.setVisible(demo);map2.setVisible(demo&&!threeD);scene.setVisible(demo&&threeD);h.ui.setVisible(!demo);for(ShapeGroup g:new ShapeGroup[]{h.background,h.observations,h.interpolations,h.sites,h.routes,h.moving,h.aircraft})g.setVisible(!demo?(g==h.background?h.layers.get("建筑背景"):g==h.observations?h.layers.get("实测点"):g==h.interpolations?h.layers.get("插值线"):g==h.sites?h.layers.get("八个研究点"):g==h.moving?h.layers.get("活动船位"):true):g==h.background&&!threeD);window.setVisible(demo&&threeD);}
 void camera(){if(window==null)return;double[] u=h.uavAt();double[] city=scenery.center();double x=harborView?city[0]-cx:follow&&u!=null?u[0]-cx:0,y=harborView?cy-city[1]:follow&&u!=null?cy-u[1]:0;double size=harborView?scenery.extent()*1.25:extent;double back=follow?420:size*.65,height=follow?300:size*.48;viewCamera.setPos(x,y-back,height);viewCamera.setRotationX(Math.atan2(height-(follow?20:0),back));viewCamera.setRotationZ(Math.PI/2);window.setCamera(viewCamera,false);window.setCamera(viewCamera,true);if(u!=null){cameraTrackedX=u[0];cameraTrackedY=u[1];}}
 void updateBuildings(boolean force){double[] u=h.uavAt();double bx=follow&&u!=null?u[0]:cx,by=follow&&u!=null?u[1]:cy;if(!force&&Double.isFinite(lastBuildingX)&&Math.hypot(bx-lastBuildingX,by-lastBuildingY)<150)return;lastBuildingX=bx;lastBuildingY=by;
  if(harborView){double[] city=scenery.center();bx=city[0];by=city[1];}scenery.update(cx,cy,bx,by,harborView?scenery.extent():extent,follow,harborView);buildingCount=scenery.buildingCount;
 }
 double[] directAt(){if(h.packet==null||!h.packet.has("trajectory")||h.packet.get("trajectory").isJsonNull())return null;double[] a=NativeWorkbench.xy(h.packet.getAsJsonArray("start_xy")),b=NativeWorkbench.xy(h.packet.getAsJsonArray("end_xy"));double length=Math.hypot(b[0]-a[0],b[1]-a[1]),travel=(h.now-t0)*15;if(travel<0||travel>length)return null;double f=length>0?travel/length:0;return new double[]{a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1])};}
 void buildingClearance(double[] u){nearestBuilding=-1;boundary=null;buildingDistance=Double.NaN;if(u==null)return;double best=Double.POSITIVE_INFINITY;JsonArray es=support.getAsJsonArray("planning_envelopes");for(int i=0;i<es.size();i++){JsonArray r=es.get(i).getAsJsonArray();double x=r.get(0).getAsDouble(),y=r.get(1).getAsDouble(),w=r.get(2).getAsDouble(),h=r.get(3).getAsDouble();double bx=Math.max(x-w,Math.min(x+w,u[0])),by=Math.max(y-h,Math.min(y+h,u[1]));double d=Math.hypot(bx-u[0],by-u[1]);if(d<best){best=d;nearestBuilding=i;boundary=new double[]{bx,by};}}buildingDistance=best;}
 void changed()throws Exception{
  result=null;closest=Double.NaN;t0=h.packet==null?0:NativeWorkbench.num(h.packet,"departure");t1=t0+1;
  if(h.packet!=null){result=h.json(Paths.get(NativeWorkbench.str(h.packet,"result_json")));JsonObject tr=result.has("trajectory")&&!result.get("trajectory").isJsonNull()?result.getAsJsonObject("trajectory"):null;
   if(tr!=null){t1=t0+NativeWorkbench.num(tr,"arrival_s")-NativeWorkbench.num(tr,"departure_s");JsonObject sc=result.getAsJsonObject("ship_check");if(sc!=null&&sc.has("closest_time_s")&&!sc.get("closest_time_s").isJsonNull())closest=NativeWorkbench.num(result,"window_start_unix_s")-h.origin+NativeWorkbench.num(sc,"closest_time_s");}
  }
  cx=(h.xmin+h.xmax)/2;cy=(h.ymin+h.ymax)/2;extent=Math.max(450,Math.max(h.xmax-h.xmin,h.ymax-h.ymin));camera();
  updateBuildings(true);
  setting=true;timeline.setRange(t0,Math.max(t0+.1,t1),false);setting=false;applyVisibility();refreshPending=true;
 }
 void sync(){try{
  h.speed=Math.max(1,Math.min(10,Math.round(h.speed)));setting=true;speedSlider.setValue(h.speed,false);setting=false;label(speedLabel,"播放速度："+(int)h.speed+"倍");
  String identity=h.key+"/"+h.runId+"/"+h.phase;if(!identity.equals(lastIdentity)){lastIdentity=identity;changed();}
  if(!demo)return;applyVisibility();double now=h.now;double[] u=h.uavAt();boolean planned=h.packet!=null&&h.packet.has("trajectory")&&!h.packet.get("trajectory").isJsonNull();
  route3.setVisible(planned&&threeD);route2.setVisible(planned&&!threeD);straight3.setVisible(planned&&threeD);straight2.setVisible(planned&&!threeD);
  if(planned){JsonArray ps=h.packet.getAsJsonObject("trajectory").getAsJsonArray("xy");points(route3,ps,35,true);points(route2,ps,0,false);double[] a=NativeWorkbench.xy(ps.get(0).getAsJsonArray()),b=NativeWorkbench.xy(ps.get(ps.size()-1).getAsJsonArray());pair(straight3,a,b,35,true);pair(straight2,a,b,0,false);}
  groundRoute.setVisible(planned&&threeD);verticalLink.setVisible(u!=null&&threeD);if(planned)points(groundRoute,h.packet.getAsJsonObject("trajectory").getAsJsonArray("xy"),.7,true);if(u!=null){verticalLink.setNPoints(2);verticalLink.setPoint(0,u[0]-cx,cy-u[1],.7);verticalLink.setPoint(1,u[0]-cx,cy-u[1],35);}
  if(follow){if(u!=null&&(!Double.isFinite(cameraTrackedX)||Math.hypot(u[0]-cameraTrackedX,u[1]-cameraTrackedY)>1e-6))camera();updateBuildings(false);}
  drone3.setVisible(u!=null&&threeD);drone2.setVisible(u!=null&&!threeD);shadow.setVisible(u!=null&&threeD);if(u!=null){drone3.setPos(u[0]-cx,cy-u[1],35);drone2.setPos(h.sx(u[0]),h.sy(u[1]));shadow.setPos(u[0]-cx,cy-u[1]);}
  double[] direction=droneDirection();uavDirection3.setVisible(u!=null&&direction!=null&&threeD);uavDirection2.setVisible(u!=null&&direction!=null&&!threeD);if(u!=null&&direction!=null){arrow(uavDirection3,u,direction,50,35,true);arrow(uavDirection2,u,direction,50,0,false);}
  double[] near=null;double distance=Double.POSITIVE_INFINITY;String nearest="";for(Ship ship:ships){ship.update(now);double[] q=h.shipAt(ship.vessel,now);if(q!=null&&u!=null){double d=Math.hypot(q[0]-u[0],q[1]-u[1]);if(d<distance){distance=d;near=q;nearest=NativeWorkbench.str(ship.vessel,"mmsi");}}}
  rangeLink3.setVisible(near!=null&&h.inside(near)&&threeD);rangeLink2.setVisible(near!=null&&h.inside(near)&&!threeD);if(near!=null){pair(rangeLink3,u,near,.8,true);pair(rangeLink2,u,near,0,false);}
  levelRing.setVisible(near!=null&&h.inside(near)&&threeD);if(near!=null)levelRing.setPos(near[0]-cx,cy-near[1],35);
  double[] ghost=compare?directAt():null;ghost3.setVisible(ghost!=null&&threeD);ghost2.setVisible(ghost!=null&&!threeD);directDistance=Double.NaN;if(ghost!=null){ghost3.setPos(ghost[0]-cx,cy-ghost[1]);ghost2.setPos(h.sx(ghost[0]),h.sy(ghost[1]));double d=Double.POSITIVE_INFINITY;for(Ship ship:ships){double[] q=h.shipAt(ship.vessel,now);if(q!=null)d=Math.min(d,Math.hypot(q[0]-ghost[0],q[1]-ghost[1]));}directDistance=d;Color color=d<90?Color.RED:new Color(210,100,50);ghost3.setFillColor(color);ghost2.setFillColor(color);}
  buildingClearance(u);boolean bd=boundary!=null&&(h.key.equals("M4")||follow);buildingLink3.setVisible(bd&&threeD);buildingLink2.setVisible(bd&&!threeD);buildingBox3.setVisible(bd&&threeD);buildingBox2.setVisible(bd&&!threeD);if(bd){pair(buildingLink3,u,boundary,1,true);pair(buildingLink2,u,boundary,0,false);JsonArray r=support.getAsJsonArray("planning_envelopes").get(nearestBuilding).getAsJsonArray();double x=r.get(0).getAsDouble(),y=r.get(1).getAsDouble(),w=r.get(2).getAsDouble(),hh=r.get(3).getAsDouble();JsonArray polygon=new JsonArray();for(double[] q:new double[][]{{x-w,y-hh},{x+w,y-hh},{x+w,y+hh},{x-w,y+hh},{x-w,y-hh}}){JsonArray p=new JsonArray();p.add(q[0]);p.add(q[1]);polygon.add(p);}points(buildingBox3,polygon,.5,true);points(buildingBox2,polygon,0,false);}
  shipDirection3.setVisible(false);shipDirection2.setVisible(false);referenceTrack3.setVisible(false);referenceTrack2.setVisible(false);String reference=h.key.equals("encounter_M1_opposing")?"477995430":h.key.equals("encounter_M1_same_direction")?"477995453":"";for(Ship ship:ships)if(reference.equals(NativeWorkbench.str(ship.vessel,"mmsi"))){double[] q=h.shipAt(ship.vessel,now),v=shipDirection(ship.vessel,now);if(q!=null&&v!=null&&h.inside(q)){shipDirection3.setVisible(threeD);shipDirection2.setVisible(!threeD);arrow(shipDirection3,q,v,45,2,true);arrow(shipDirection2,q,v,45,0,false);Color color=q[2]==1?h.blue:h.orange;shipDirection3.setLineColor(color);shipDirection2.setLineColor(color);for(JsonElement se:ship.vessel.getAsJsonArray("segments")){JsonArray seg=se.getAsJsonArray();for(int i=0;i+1<seg.size();i++){JsonObject a=seg.get(i).getAsJsonObject(),b=seg.get(i+1).getAsJsonObject();if(NativeWorkbench.num(a,"t")<=now&&now<=NativeWorkbench.num(b,"t")){pair(referenceTrack3,NativeWorkbench.xy(a.getAsJsonArray("xy")),NativeWorkbench.xy(b.getAsJsonArray("xy")),1,true);pair(referenceTrack2,NativeWorkbench.xy(a.getAsJsonArray("xy")),NativeWorkbench.xy(b.getAsJsonArray("xy")),0,false);referenceTrack3.setVisible(threeD);referenceTrack2.setVisible(!threeD);}}}}}
  boolean endpoints=h.packet!=null;start3.setVisible(endpoints&&threeD);end3.setVisible(endpoints&&threeD);start2.setVisible(endpoints&&!threeD);end2.setVisible(endpoints&&!threeD);startLabel.setVisible(endpoints&&!threeD);endLabel.setVisible(endpoints&&!threeD);if(endpoints){double[] a=NativeWorkbench.xy(h.packet.getAsJsonArray("start_xy")),b=NativeWorkbench.xy(h.packet.getAsJsonArray("end_xy"));start3.setPos(a[0]-cx,cy-a[1]);end3.setPos(b[0]-cx,cy-b[1]);start2.setPos(h.sx(a[0]),h.sy(a[1]));end2.setPos(h.sx(b[0]),h.sy(b[1]));startLabel.setPos(h.sx(a[0])+10,h.sy(a[1])+10);endLabel.setPos(h.sx(b[0])+10,h.sy(b[1])+10);}
  String hk=Instant.ofEpochMilli((long)((h.origin+now)*1000)).atZone(ZoneId.of("Asia/Hong_Kong")).format(DateTimeFormatter.ofPattern("HH:mm:ss.SSS"));label(clock,"香港时间 "+hk+String.format(Locale.ROOT,"   |   任务 %.1f / %.1f 秒   |   %s",Math.max(0,now-t0),Math.max(0,t1-t0),(threeD?"三维展示":"二维展示")+" / "+(int)h.speed+"倍"));
  if(h.phase.equals("error"))label(clock,"任务失败，已恢复操作；可重新读取或规划。");else if(h.busy||h.packet==null)label(clock,"正在读取任务结果，请稍候…");else if(!planned)label(clock,"香港时间 "+hk+"   |   未出发：没有可回放路线");
  String min="不可计算",direct="未另行验算";if(result!=null&&result.has("ship_check")&&!result.get("ship_check").isJsonNull()){JsonObject sc=result.getAsJsonObject("ship_check");if(sc.has("minimum_distance_m")&&!sc.get("minimum_distance_m").isJsonNull())min=String.format(Locale.ROOT,"%.3f 米",NativeWorkbench.num(sc,"minimum_distance_m"));}
  JsonObject registry=support.getAsJsonObject("case_checks");if(registry.has(h.runId)){JsonObject c=registry.getAsJsonObject(h.runId).getAsJsonObject("direct_check");if(!c.get("minimum_distance_m").isJsonNull())direct=String.format(Locale.ROOT,"%.3f 米",NativeWorkbench.num(c,"minimum_distance_m"));}
  label(stats,routeDescription()+"\n海上巡航段（不含码头起降）\n"+(h.packet==null?(h.phase.equals("error")?"本次任务失败":"正在读取…"):NativeWorkbench.str(h.packet,"label"))+"\n\n此刻水平中心船距："+(Double.isFinite(distance)?String.format(Locale.ROOT,"%.2f 米",distance):"不可计算")+"\n全程最小中心船距："+min+"\n最近船号："+(nearest.isEmpty()?"此刻无可计算船位":nearest));
  JsonObject bc=support.getAsJsonObject("building_checks");String bmin=bc.has(h.runId)?String.format(Locale.ROOT,"%.2f 米",NativeWorkbench.num(bc.getAsJsonObject(h.runId),"minimum_rectangle_clearance_m")):"未另行验算";
  label(detail,"建筑包络距离："+(Double.isFinite(buildingDistance)?String.format(Locale.ROOT,"%.2f 米",buildingDistance):"不可计算")+" / 要求≥30米\n全程最小建筑距离："+bmin+"\n"+(compare?(Double.isFinite(directDistance)?String.format(Locale.ROOT,"假如直飞，此刻船距 %.2f米%s",directDistance,directDistance<90?"（冲突）":""):"直飞对照已到达／此刻无有效船位"):"直飞对照已关闭"));
  label(story,h.phase.equals("error")?"本次作业失败，未显示旧路线。\n\n"+h.status.getText()+"\n\n可重新读取结果或重试规划。":h.busy?"正在读取结果，旧路线和无人机已清除。":planned?explanation(direct):"此任务没有可回放的无人机路线。\n\n"+h.phase+"\n"+(h.packet==null?"":h.reason(NativeWorkbench.str(h.packet,"reason")))+"\n\n拒绝出发也是正确结果。\n不通过换时间或降低标准刷成功。");
  setting=true;timeline.setValue(Math.max(t0,Math.min(t1,now)),false);setting=false;String geometry=h.key+"/"+h.phase+"/"+now+"/"+threeD+"/"+cx+"/"+cy+"/"+compare+"/"+h.playing;if(!geometry.equals(lastGeometry)){lastGeometry=geometry;resetTree(drone3);resetTree(route3);resetTree(straight3);resetTree(shadow);resetTree(rangeLink3);resetTree(uavDirection3);resetTree(shipDirection3);for(Shape s:new Shape[]{groundRoute,verticalLink,buildingLink3,buildingBox3,ghost3,levelRing,referenceTrack3})resetTree(s);for(Ship ship:ships){resetTree(ship.mesh);resetTree(ship.ring3);}}
 }catch(Exception ex){error=ex.toString();label(story,"展示错误："+error);}}
 void label(ShapeText text,String value){if(!Objects.equals(text.getText(),value)){text.setText(value);text.resetSVGComponent();}}
 void resetTree(Shape shape){if(shape instanceof ShapeGroup)for(Object o:((ShapeGroup)shape).getShapes())if(o instanceof Shape)resetTree((Shape)o);shape.resetSVGComponent();}
 void writeState(){try{JsonObject s=new JsonObject();s.addProperty("follow_camera",follow);s.addProperty("harbor_view",harborView);s.addProperty("official_height_buildings",scenery.knownHeights);s.addProperty("compare",compare);s.addProperty("nearest_building_index",nearestBuilding);if(Double.isFinite(buildingDistance))s.addProperty("building_distance_m",buildingDistance);if(Double.isFinite(directDistance))s.addProperty("direct_distance_m",directDistance);if(boundary!=null){JsonArray b=new JsonArray();b.add(boundary[0]);b.add(boundary[1]);s.add("building_boundary_xy",b);}s.addProperty("demo",demo);s.addProperty("three_d",threeD);s.addProperty("key",h.key);s.addProperty("route_id",currentRouteId());s.addProperty("phase",h.phase);s.addProperty("busy",h.busy);s.addProperty("run_id",h.runId);s.addProperty("time",h.now);s.addProperty("playing",h.playing);s.addProperty("speed",h.speed);s.addProperty("closest_capture_s",Double.isFinite(closest)?closest:-1);s.addProperty("buildings",buildingCount);s.addProperty("error",error);double[] u=h.uavAt();s.addProperty("uav_visible",u!=null);s.addProperty("native_drone_visible",drone3.isVisible());s.addProperty("native_drone_x",drone3.getX());s.addProperty("native_drone_y",drone3.getY());s.addProperty("native_drone_z",drone3.getZ());s.addProperty("native_drone_svg_id",drone3.getSVGId());s.addProperty("native_route_visible",route3.isVisible());if(droneDirection()!=null){JsonArray dv=new JsonArray();for(double value:droneDirection())dv.add(value);s.add("uav_direction_xy",dv);}s.addProperty("uav_arrow_id",uavDirection3.getSVGId());if(u!=null){JsonArray q=new JsonArray();q.add(u[0]);q.add(u[1]);s.add("uav_xy",q);s.addProperty("display_z",35);}JsonArray shipData=new JsonArray();JsonArray directions=new JsonArray();for(Ship ship:ships){double[] q=h.shipAt(ship.vessel,h.now);if(q==null)continue;JsonObject v=new JsonObject();v.addProperty("mmsi",NativeWorkbench.str(ship.vessel,"mmsi"));JsonArray xy=new JsonArray();xy.add(q[0]);xy.add(q[1]);v.add("xy",xy);v.addProperty("measured",q[2]==1);JsonObject render=new JsonObject();render.addProperty("mmsi",NativeWorkbench.str(ship.vessel,"mmsi"));double[] heading=shipDirection(ship.vessel,h.now);render.addProperty("direction_known",heading!=null);render.addProperty("mesh_id",ship.mesh.getSVGId());render.addProperty("icon_id",ship.icon.getSVGId());render.addProperty("angle_rad",ship.mesh.getRotation());if(heading!=null){JsonArray hv=new JsonArray();for(double value:heading)hv.add(value);render.add("direction_xy",hv);}directions.add(render);shipData.add(v);}s.add("ships",shipData);s.add("render_directions",directions);Path dir=h.root.resolve("anylogic/visual_demo");Path tmp=dir.resolve("state.tmp");Files.writeString(tmp,s.toString(),StandardCharsets.UTF_8);Files.move(tmp,dir.resolve("state.json"),StandardCopyOption.REPLACE_EXISTING);}catch(Exception ignored){}}
 void pulse(){h.viewHook=()->{try{if(!initial&&!h.busy){initial=true;load("encounter_M1_same_direction","遇船案例");}if(demo&&h.playing&&h.now>=t1){h.now=t1;h.playing=false;h.draw();}sync();if(focusWhenReady&&!h.busy){focusWhenReady=false;h.now=focusTime();h.playing=false;h.draw();sync();}if(refreshPending&&!h.busy){refreshPending=false;resetTree(scene);}if(++ticks%5==0)writeState();}catch(Exception e){error=e.toString();}};}
}
