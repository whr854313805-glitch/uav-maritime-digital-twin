package maritime.security;

import java.lang.instrument.*;
import java.security.ProtectionDomain;
import java.util.*;
import jdk.internal.org.objectweb.asm.*;

/** In-memory, project-scoped loopback binding for the fixed AnyLogic Java 17 runtime.
 * Covers model HTTP, editor IPC and the database child. Installed files are untouched.
 * No global firewall change, admin privilege or publisher trust claim is involved.
 */
public final class LoopbackAgent {
 private static volatile boolean applied=false;
 public static boolean enforced(){return applied;}
 public static void premain(String options, Instrumentation instrumentation) {
  try {
   if(Runtime.version().feature()!=17)throw new IllegalStateException("AnyLogic Java 17 required");
   Module base=Object.class.getModule(),ours=LoopbackAgent.class.getModule();
   instrumentation.redefineModule(base,Set.of(),Map.of("jdk.internal.org.objectweb.asm",Set.of(ours)),Map.of(),Set.of(),Map.of());
   instrumentation.addTransformer(new ClassFileTransformer() {
    public byte[] transform(ClassLoader loader,String name,Class<?> clazz,ProtectionDomain domain,byte[] bytes) {
     if(!"sun/nio/ch/Net".equals(name))return null;
     try {
      ClassReader reader=new ClassReader(bytes);ClassWriter writer=new ClassWriter(reader,0);int[] changed={0};
      reader.accept(new ClassVisitor(Opcodes.ASM8,writer) {
       public MethodVisitor visitMethod(int access,String method,String descriptor,String signature,String[] exceptions) {
        MethodVisitor visitor=super.visitMethod(access,method,descriptor,signature,exceptions);
        if(!method.equals("bind") || !descriptor.equals("(Ljava/net/ProtocolFamily;Ljava/io/FileDescriptor;Ljava/net/InetAddress;I)V"))return visitor;
        changed[0]++;
        return new MethodVisitor(Opcodes.ASM8,visitor) {
         public void visitCode(){super.visitCode();super.visitLdcInsn("127.0.0.1");
          super.visitMethodInsn(Opcodes.INVOKESTATIC,"java/net/InetAddress","getByName","(Ljava/lang/String;)Ljava/net/InetAddress;",false);
          super.visitVarInsn(Opcodes.ASTORE,2);}
        };
       }
      },0);
      if(changed[0]!=1)throw new IllegalStateException("Unsupported Net.bind layout");
      applied=true;return writer.toByteArray();
     } catch(Throwable error){System.err.println("Project network guard failed: "+error);Runtime.getRuntime().halt(78);return null;}
    }
   },true);
   Class<?> net=Class.forName("sun.nio.ch.Net",true,null);
   instrumentation.retransformClasses(net);
   if(!applied)throw new IllegalStateException("Loopback transformation was not applied");
  } catch(Throwable error){System.err.println("Project network guard could not start: "+error);Runtime.getRuntime().halt(78);}
 }
}
