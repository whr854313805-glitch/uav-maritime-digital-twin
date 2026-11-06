package maritime;

import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.time.Instant;

/** Bounded jobs and shutdown cleanup; only handles belonging to this model. */
public final class OwnedJobs {
 private static final Set<Process> ACTIVE=ConcurrentHashMap.newKeySet();
 static { Runtime.getRuntime().addShutdownHook(new Thread(()->{
   for(Process process:ACTIVE)stop(process);
 },"owned-python-shutdown")); }
 public static void run(List<String> args,Path root,Path log,long seconds)throws Exception {
  Process process=new ProcessBuilder(args).directory(root.toFile()).redirectErrorStream(true).redirectOutput(log.toFile()).start();
  ACTIVE.add(process);
  try {
   if(!process.waitFor(seconds,TimeUnit.SECONDS))throw new TimeoutException("Python作业超时（"+seconds+"秒），本次作业已终止；见 "+log);
   if(process.exitValue()!=0)throw new java.io.IOException("Python作业失败（退出码"+process.exitValue()+"），见 "+log);
  } finally {if(process.isAlive())stop(process);ACTIVE.remove(process);}
 }
 private static boolean same(ProcessHandle handle,Instant start) {
  return handle.isAlive() && handle.info().startInstant().map(v->v.equals(start)).orElse(false);
 }
 public static void stop(Process process) {
  if(!process.isAlive())return;
  Map<ProcessHandle,Instant> owned=new LinkedHashMap<>();
  process.descendants().forEach(h->h.info().startInstant().ifPresent(t->owned.put(h,t)));
  process.toHandle().info().startInstant().ifPresent(t->owned.put(process.toHandle(),t));
  owned.forEach((h,t)->{if(same(h,t))h.destroy();});
  try {process.waitFor(1500,TimeUnit.MILLISECONDS);}catch(InterruptedException e){Thread.currentThread().interrupt();}
  owned.forEach((h,t)->{if(same(h,t))h.destroyForcibly();});
 }
}
