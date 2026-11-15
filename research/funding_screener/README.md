# Funding Spread Radar

Trang web live tìm cơ hội delta-neutral (long sàn này / short sàn kia để ăn chênh lệch funding) trên các perp DEX.
Chỉ dùng thư viện chuẩn của Python, không cần `pip install`. Đặc tả kỹ thuật: `docs/06_quant_research/funding-screener.md`.

## Deploy public lên Render (miễn phí)

1. Tạo tài khoản tại https://render.com (đăng nhập bằng GitHub `vinhk688-hub` cho nhanh) và cho Render quyền đọc repo `rsi_bot`.
2. **Cách A, Blueprint:** Dashboard → **New** → **Blueprint** → chọn repo `rsi_bot`, nhánh có file `render.yaml` (sau khi PR được merge thì là `mua-tren-the-nang`) → **Apply**.
3. **Cách B, thủ công:** **New** → **Web Service** → chọn repo, rồi điền:
   - Language: `Python 3`, Branch: nhánh chứa code, Region: `Singapore`
   - Root Directory: `research/funding_screener`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python screener.py`
   - Instance type: `Free`, Health Check Path (Advanced): `/healthz`
4. Đợi build xong, mở link dạng `https://funding-spread-radar.onrender.com`. Lần đầu mất khoảng 1 phút để lấy snapshot, lịch sử 30 ngày điền dần trong 5–10 phút.

Lưu ý gói Free của Render: service ngủ sau 15 phút không ai truy cập, lần mở lại mất ~1 phút để khởi động và cache lịch sử bị xoá (tự tải lại). Muốn luôn thức: dùng gói Starter, hoặc đặt UptimeRobot ping `/healthz` mỗi 5 phút.

## Chạy trên máy

```bash
cd research/funding_screener
python screener.py          # mở http://localhost:8787
```

## Đọc bảng

| Cột | Ý nghĩa |
|---|---|
| APR now / 24h / 7d / 30d | Spread funding (short − long, có dấu) quy ra APR |
| Sust 30d | % số giờ trong 30 ngày spread trả đúng chiều |
| Risk | LOW / MED / HIGH từ độ biến động spread 7 ngày (ước lượng riêng) |
| Hoà vốn | Phí vào + ra cả hai chân + bid/ask, chia cho spread kỳ vọng = min(now, 7d). `*` = bid/ask giả định |
| OI min | OI nhỏ hơn trong hai chân, kèm hạng size SKIP / SMALL / OK / ROOM |
| Cờ | ⚡ đột biến, ⇄ đổi chiều, 📅 cổ phiếu/RWA cuối tuần, ⏳ lịch sử < 72h |

Bấm nút **Phí & trượt giá** để sửa phí theo tier của bạn (lưu trên trình duyệt). Bấm vào một dòng để xem biểu đồ spread 30 ngày và checklist.

Không phải lời khuyên đầu tư. Luôn kiểm tra lại funding, phí và OI trên giao diện sàn trước khi vào lệnh.
