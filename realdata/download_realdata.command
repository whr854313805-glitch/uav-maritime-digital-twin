#!/bin/bash
# 一键下载维多利亚港真实船舶数据
# 双击运行即可

set -e
cd "$(dirname "$0")"

echo "===== 下载真实数据中 ====="
echo ""

echo "[1/3] Star Ferry 中环-尖沙咀官方时刻表 CSV..."
curl -fL -o starferry_central_tst_timetable.csv \
  'https://www.starferry.com.hk/sites/default/files/ferry_sf_central_tsimshatsui_timetable_updatedon022018_eng.csv'

echo ""
echo "[2/3] 香港海事处实时在港船舶 XML..."
curl -fL -o mardep_in_port.xml \
  'https://www.mardep.gov.hk/e_files/en/opendata/RP06005i.XML'

echo ""
echo "[3/3] Star Ferry 尖沙咀-湾仔时刻表 PDF (备用)..."
curl -fL -o starferry_tst_wanchai_timetable.pdf \
  'https://www.starferry.com.hk/sites/default/files/Wanchai-Tsim%20Sha%20Tsui%20Service_Eng.pdf' || \
  echo "  (尖沙咀-湾仔 PDF 下载失败,但不影响主流程)"

echo ""
echo "===== 下载完成 ====="
ls -la
echo ""
echo "现在可以告诉 Claude '下完了',它会用真实数据重新生成 vessel_positions.csv"
echo ""
read -n 1 -s -r -p "按任意键关闭窗口..."
