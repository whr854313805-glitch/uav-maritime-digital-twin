package maritime;

import com.google.gson.*;

/** Reject contradictory success packets before any native success UI is set. */
public final class ResultPacket {
 public static void validate(JsonObject packet) {
  if(!packet.has("status") || !"planned".equals(packet.get("status").getAsString()))return;
  JsonObject checks=packet.getAsJsonObject("checks"),ship=packet.getAsJsonObject("ship_check"),tr=packet.getAsJsonObject("trajectory");
  for(String name:new String[]{"ships","geometry","coverage"})
   if(checks==null || !truth(checks.get(name)))throw new IllegalStateException("成功结果的检查状态不一致："+name);
  if(ship==null || !truth(ship.get("valid")) || tr==null)throw new IllegalStateException("成功结果缺少有效检查或航迹");
  JsonElement distance=tr.get("distance_m");
  if(distance==null || !distance.isJsonPrimitive() || !distance.getAsJsonPrimitive().isNumber()
   || !Double.isFinite(distance.getAsDouble()) || distance.getAsDouble()<=0)throw new IllegalStateException("成功结果的航程无效");
 }
 private static boolean truth(JsonElement value) {
  return value!=null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isBoolean() && value.getAsBoolean();
 }
}
