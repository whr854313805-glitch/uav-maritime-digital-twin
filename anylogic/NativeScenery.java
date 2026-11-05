package maritime;

import com.anylogic.engine.presentation.*;
import com.google.gson.*;
import java.awt.Color;
import java.awt.Font;
import java.util.*;

/** Read-only offline scenery. Never supplies geometry/heights to the planner. */
final class NativeScenery {
 final NativeWorkbench h;final ShapeGroup group;final JsonObject data;
 final ArrayList<ShapePolyLine> land=new ArrayList<>(),coast=new ArrayList<>(),green=new ArrayList<>();
 final ArrayList<JsonArray> greenGeometry=new ArrayList<>();
 final ArrayList<Building> pool=new ArrayList<>();final ArrayList<Marker> markers=new ArrayList<>();
 final Color water=new Color(53,113,140),landColor=new Color(220,224,211),shore=new Color(188,216,208);
 int buildingCount=0,knownHeights=0;double ox=Double.NaN,oy=Double.NaN;
 static final ShapeDrawMode D3=ShapeDrawMode.SHAPE_DRAW_3D;
 NativeScenery(NativeWorkbench host,ShapeGroup parent)throws Exception{
  h=host;data=h.json(h.root.resolve("anylogic/visual_demo/scenery.json"));
  if(!data.get("display_only").getAsBoolean())throw new IllegalStateException("Scenery must remain display-only");
  group=new ShapeGroup(h.owner,D3,true,0,0,0,0);parent.add(group);
  group.add(new ShapeRectangle(D3,true,-18000,-18000,-5,0,water,water,36000,36000,2,1,LineStyle.LINE_STYLE_SOLID));
  for(int i=0;i<22;i++)group.add(new ShapeRectangle(D3,true,-16000,-11000+i*1000,-2.9,0,new Color(57,119,146),new Color(57,119,146),32000,16,0,0,LineStyle.LINE_STYLE_SOLID));
  for(JsonElement e:data.getAsJsonArray("land"))land.add(poly(landColor,landColor,.3));
  for(JsonElement e:data.getAsJsonArray("coastlines")){ShapePolyLine p=poly(shore,null,0);p.setLineWidth(2);coast.add(p);}
  // Select large real vegetation pieces for a quiet background, not every tiny ring.
  ArrayList<JsonArray> patches=new ArrayList<>();for(JsonElement e:data.getAsJsonArray("vegetation"))patches.add(e.getAsJsonArray());
  patches.sort((a,b)->Double.compare(area(b),area(a)));
  for(int i=0;i<Math.min(100,patches.size());i++){greenGeometry.add(patches.get(i));green.add(poly(new Color(135,164,134),new Color(146,176,143),.2));}
  for(int i=0;i<360;i++)pool.add(new Building());
  for(JsonElement e:data.getAsJsonArray("landmarks"))markers.add(new Marker(e.getAsJsonObject()));
 }
 double area(JsonArray ps){double result=0;for(int i=0;i+1<ps.size();i++){double[] a=NativeWorkbench.xy(ps.get(i).getAsJsonArray()),b=NativeWorkbench.xy(ps.get(i+1).getAsJsonArray());result+=a[0]*b[1]-a[1]*b[0];}return Math.abs(result)/2;}
 ShapePolyLine poly(Color line,Color fill,double height){ShapePolyLine p=new ShapePolyLine(D3,true,0,0,0,line,fill,2,new double[]{0,0},new double[]{0,0},new double[]{0,0},fill!=null,height,1,LineStyle.LINE_STYLE_SOLID);group.add(p);return p;}
 void points(ShapePolyLine p,JsonArray ps,double z,double cx,double cy){p.setNPoints(ps.size());for(int i=0;i<ps.size();i++){double[] q=NativeWorkbench.xy(ps.get(i).getAsJsonArray());p.setPoint(i,q[0]-cx,cy-q[1],z);}}
 void reset(Shape s){s.resetSVGComponent();}
 double[] center(){return NativeWorkbench.xy(data.getAsJsonArray("overview_center_xy"));}
 double extent(){return data.get("overview_extent_m").getAsDouble();}
 void update(double cx,double cy,double focusX,double focusY,double extent,boolean follow,boolean panorama){
  if(cx!=ox||cy!=oy){
   ox=cx;oy=cy;
   for(int i=0;i<land.size();i++){points(land.get(i),data.getAsJsonArray("land").get(i).getAsJsonArray(),-.6,cx,cy);reset(land.get(i));}
   for(int i=0;i<coast.size();i++){points(coast.get(i),data.getAsJsonArray("coastlines").get(i).getAsJsonArray(),.1,cx,cy);reset(coast.get(i));}
   for(int i=0;i<green.size();i++){points(green.get(i),greenGeometry.get(i),-.1,cx,cy);reset(green.get(i));}
  }
  double reach=panorama?extent:follow?1400:Math.max(1500,extent*1.25);
  ArrayList<JsonObject> candidates=new ArrayList<>();
  for(JsonElement e:data.getAsJsonArray("buildings")){JsonObject b=e.getAsJsonObject();double[] p=NativeWorkbench.xy(b.getAsJsonArray("center"));if(Math.hypot(p[0]-focusX,p[1]-focusY)<reach)candidates.add(b);}
  // Every landmark and prominent skyline building is considered; nearby detail fills the rest.
  candidates.sort(Comparator.comparingDouble(b->{double[] p=NativeWorkbench.xy(b.getAsJsonArray("center"));double distance=Math.hypot(p[0]-focusX,p[1]-focusY);if(!b.get("landmark").getAsString().isEmpty())return -100000.;double height=b.get("height_m").getAsDouble();return distance-height*(panorama?3:2);}));
  if(panorama){LinkedHashMap<String,JsonObject> selected=new LinkedHashMap<>();for(JsonElement e:data.getAsJsonArray("landmarks")){JsonObject landmark=e.getAsJsonObject();selected.put(landmark.get("id").getAsString()+landmark.get("center"),landmark);}for(JsonElement e:data.getAsJsonArray("landmarks")){double[] anchor=NativeWorkbench.xy(e.getAsJsonObject().getAsJsonArray("center"));ArrayList<JsonObject> local=new ArrayList<>(candidates);local.sort(Comparator.comparingDouble(b->{double[] p=NativeWorkbench.xy(b.getAsJsonArray("center"));return Math.hypot(p[0]-anchor[0],p[1]-anchor[1]);}));for(int i=0;i<Math.min(35,local.size());i++){JsonObject f=local.get(i);selected.put(f.get("id").getAsString()+f.get("center"),f);}}for(JsonObject f:candidates)selected.putIfAbsent(f.get("id").getAsString()+f.get("center"),f);candidates=new ArrayList<>(selected.values());}
  buildingCount=Math.min(panorama?360:follow?120:200,candidates.size());knownHeights=0;
  for(int i=0;i<pool.size();i++){Building b=pool.get(i);boolean visible=i<buildingCount;b.visible(visible);if(visible){JsonObject f=candidates.get(i);b.apply(f,cx,cy);if(f.get("height_source").getAsString().equals("official_top_minus_base"))knownHeights++;}}
  for(Marker marker:markers)marker.update(cx,cy,focusX,focusY,reach,panorama);
 }
 final class Building{
  final ShapePolyLine shell=poly(new Color(111,135,148),new Color(168,190,200),40),roof=poly(new Color(234,242,242),new Color(216,230,230),0);
  final ShapePolyLine[] bands={poly(new Color(209,225,230),null,0),poly(new Color(209,225,230),null,0),poly(new Color(209,225,230),null,0)};
  void visible(boolean on){shell.setVisible(on);roof.setVisible(on);for(ShapePolyLine p:bands)p.setVisible(on);}
  void apply(JsonObject f,double cx,double cy){double height=f.get("height_m").getAsDouble();JsonArray ps=f.getAsJsonArray("xy");boolean known=f.get("height_source").getAsString().equals("official_top_minus_base"),landmark=!f.get("landmark").getAsString().isEmpty();
   Color fill=!known?new Color(211,203,187):height>150?new Color(125,177,199):height>70?new Color(160,194,205):new Color(210,219,214);
   shell.setFillColor(fill);shell.setLineColor(landmark?new Color(98,140,158):new Color(151,171,179));shell.setZHeight(height);points(shell,ps,0,cx,cy);points(roof,ps,height+.15,cx,cy);
   for(int i=0;i<bands.length;i++){bands[i].setVisible(height>45);points(bands[i],ps,height*(i+1)/4,cx,cy);reset(bands[i]);}reset(shell);reset(roof);
  }
 }
 final class Marker{
  final JsonObject source;final ShapeText label;final ShapePolyLine stem=poly(new Color(219,174,91),null,0);final ShapeOval pin;
  Marker(JsonObject f){source=f;label=new ShapeText(D3,true,0,0,0,Math.PI,new Color(25,53,71),f.get("landmark").getAsString(),new Font("Arial",Font.BOLD,24),TextAlignment.ALIGNMENT_CENTER);group.add(label);pin=new ShapeOval(D3,true,0,0,0,0,new Color(225,180,99),new Color(238,204,145),7,7,1,1,LineStyle.LINE_STYLE_SOLID);group.add(pin);}
  void update(double cx,double cy,double fx,double fy,double reach,boolean panorama){double[] q=NativeWorkbench.xy(source.getAsJsonArray("center"));boolean visible=Math.hypot(q[0]-fx,q[1]-fy)<reach;label.setVisible(visible);stem.setVisible(visible);pin.setVisible(visible);if(!visible)return;label.setFont(new Font("Arial",Font.BOLD,panorama?85:28));double z=source.get("height_m").getAsDouble()+12;double x=q[0]-cx,y=cy-q[1];label.setPos(x,y,z+18);pin.setPos(x,y,z);stem.setNPoints(2);stem.setPoint(0,x,y,z-12);stem.setPoint(1,x,y,z);reset(label);reset(pin);reset(stem);}
 }
}
