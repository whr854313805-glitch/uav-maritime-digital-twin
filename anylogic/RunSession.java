package maritime;

import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;

/** Called by the locally generated model, before installing input controls. */
public final class RunSession {
 public static void register(String project,String launchId,String model)throws Exception {
  boolean enforced=Boolean.TRUE.equals(Class.forName("maritime.security.LoopbackAgent",true,ClassLoader.getSystemClassLoader()).getMethod("enforced").invoke(null));
  if(!enforced)throw new IllegalStateException("本项目网络保护未生效，拒绝启动模型。");
  Path root=Paths.get(project).toRealPath();
  JsonObject launch=JsonParser.parseString(Files.readString(root.resolve(".local/launcher-state.json"))).getAsJsonObject();
  if(!launchId.equals(launch.get("launch_id").getAsString()) || !launchId.equals(System.getenv("UAV_RUN_ID"))
   || !root.equals(Paths.get(launch.get("project_root").getAsString()).toRealPath()))throw new IllegalStateException("启动身份不匹配。");
  ProcessHandle self=ProcessHandle.current();
  JsonObject record=new JsonObject();record.addProperty("project_root",root.toString());record.addProperty("launch_id",launchId);
  record.addProperty("java_pid",self.pid());record.addProperty("java_start_ms",self.info().startInstant().orElseThrow().toEpochMilli());
  record.addProperty("workspace",launch.get("workspace").getAsString());record.addProperty("model",model);
  record.addProperty("loopback_only",true);
  Path target=root.resolve(".local/model-session.json"),tmp=root.resolve(".local/model-session."+self.pid()+".tmp");
  Files.writeString(tmp,record.toString(),StandardCharsets.UTF_8);Files.move(tmp,target,StandardCopyOption.REPLACE_EXISTING);
 }
}
