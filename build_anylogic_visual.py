"""Build an additional native presentation model; accepted workstation unchanged."""
from pathlib import Path
import subprocess
from portable_runtime import find_anylogic
P=Path(__file__).resolve().parent;A=find_anylogic();D=P/'anylogic';plugins=A/'plugins';J=A/'jre/bin'
gson=next(plugins.glob('com.google.gson_*.jar'));cp=';'.join([*(str(p) for p in plugins.glob('com.anylogic.engine*/*.jar')),str(gson)])
for f in [D/'NativeDemoView.java']:
 f.write_text(f.read_text(encoding='utf-8-sig'),encoding='utf-8')
adapted=D/'visual_sources/NativeWorkbench.java';adapted.parent.mkdir(exist_ok=True)
host=(D/'NativeWorkbench.java').read_text(encoding='utf-8');assert host.count('"/ais_workbench/"')==1
assert host.count('ShapeGroup g=new ShapeGroup(owner);')==1
adapted_host=host.replace('"/ais_workbench/"','"/ais_visual_demo/"').replace('ShapeGroup g=new ShapeGroup(owner);','ShapeGroup g=new ShapeGroup(owner,ShapeDrawMode.SHAPE_DRAW_2D,true,0,0,0,0);')
# The presentation and its workbench share one playback clock, capped at 10x.
assert host.count('new String[]{"10倍","30倍","60倍"}')==1
adapted_host=adapted_host.replace('new String[]{"10倍","30倍","60倍"}', 'new String[]{"1倍","2倍","5倍","10倍"}').replace('new double[]{10,30,60}[getValueIndex()]','new double[]{1,2,5,10}[getValueIndex()]').replace('speedBox.setValueIndex(0,false);button(ui,405','speedBox.setValueIndex(3,false);button(ui,405').replace('speed=speed==10?30:speed==30?60:10','speed=speed==1?2:speed==2?5:speed==5?10:1')
assert adapted_host.count('  double[] uav;')==1
adapted_host=adapted_host.replace('  double[] uav;','  Runnable viewHook;double[] uav;')
assert adapted_host.count('if(++frame%5==0)writeState();')==1
adapted_host=adapted_host.replace('if(++frame%5==0)writeState();','if(viewHook!=null)viewHook.run();if(++frame%5==0)writeState();')
adapted.write_text(adapted_host,encoding='utf-8')

subprocess.run([str(J/'javac.exe'),'-encoding','UTF-8','-classpath',cp,'-d',str(D/'visual_classes'),str(adapted),str(D/'NativeDemoView.java'),str(D/'NativeScenery.java'),str(D/'OwnedJobs.java'),str(D/'RunSession.java'),str(D/'ResultPacket.java')],check=True)
subprocess.run([str(J/'jar.exe'),'--create','--file',str(D/'native-visual-demo.jar'),'-C',str(D/'visual_classes'),'.'],check=True)
print('Built current presentation JAR; model template preserved.')

agent=D/'agent_classes';agent.mkdir(exist_ok=True)
subprocess.run([str(J/'javac.exe'),'--add-exports','java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED','-encoding','UTF-8','-d',str(agent),str(D/'LoopbackAgent.java')],check=True)
manifest=agent/'MANIFEST.MF';manifest.write_text('Manifest-Version: 1.0\nPremain-Class: maritime.security.LoopbackAgent\nCan-Retransform-Classes: true\n\n',encoding='ascii')
subprocess.run([str(J/'jar.exe'),'--create','--file',str(D/'loopback-agent.jar'),'--manifest',str(manifest),'-C',str(agent),'maritime'],check=True)
