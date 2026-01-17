================================================================================
                        DICOM 下載工具 - README
================================================================================

概述
----
本工具透過病人 ID、檢查日期與模態，從 PACS 伺服器下載 DICOM 影像。
支援多伺服器，並包含逾時處理以跳過問題下載。


安裝
----
1. 將 FuDownload 資料夾解壓縮到 Windows 電腦任一位置
2. 無需安裝，解壓後即可使用
3. 所有 Python 相依套件已包含在封裝內


設定
----
1. 編輯 config.yaml 以新增 DICOM 伺服器：
   - ae_title: PACS 伺服器的 AE Title
   - ip: 伺服器 IP
   - port: 伺服器連接埠（通常為 11112）
   - description: 伺服器友善名稱

2. 視需要調整 config.yaml 內逾時設定：
   - query_timeout: C-FIND 查詢最大時間（預設 30 秒）
   - download_timeout: C-MOVE 下載最大時間（預設 120 秒）


使用方式
--------

1. 批次處理（建議）
   編輯 queries.csv 病例清單後執行：
   > run.bat --batch queries.csv

   CSV 格式（建議有標題列，可省略）：
   標題列（建議）：PatientID,StudyDate,Modality,Server
   第 1 欄：PatientID（例如 8318169 或 PAT001）
   第 2 欄：日期格式 YYYY-MM-DD（例如 2025-09-22）
   第 3 欄：Modality（例如 CT, MR, US）
   第 4 欄：config.yaml 內的伺服器名稱（例如 LK, LNK）

   範例：
   8318169, 2019-05-20, CT, LK
   PAT001, 2025-09-22, MR, LNK
   12345, 2025-09-21, US, LK

   注意：以 # 開頭的行會視為註解並忽略


2. 批次 + 傳輸包裝（分批下載、壓縮/直傳、傳輸）
   依病例數分批下載（預設每批 20 筆），每批完成後：
   - zip 模式（預設）：
     1) 將 GENERAL 內所有資料夾壓成 zip
     2) 刪除 GENERAL 內原始資料
     3) 透過 FuTransfer 傳送 zip
     4) 傳送成功後刪除 zip，繼續下一批
   - direct 模式（FuTransfer 直傳）：
     1) 直接透過 FuTransfer 傳送 GENERAL
     2) 傳送成功後再清空 GENERAL

   執行方式：
   > run_with_transfer.bat queries.csv --transfer-server 192.168.1.100
   > run_with_transfer.bat C:\case_lists --transfer-server 192.168.1.100
   > run_with_transfer.bat queries.csv --transfer-server 192.168.1.100 --transfer-mode direct
   > run_with_transfer.bat queries.csv --transfer-server 192.168.1.100 --transfer-protocol batch

   說明：
   - FuTransfer 預設位於 C:\FuTransfer（可用 --transfer-root 指定）
   - GENERAL 路徑預設取自 config.yaml 的 move_destination.storage_path
   - 其他參數會直接傳給 dicom_downloader（例如 --timeout 180）
   - 每批大小可用 --batch-size 變更（例如 --batch-size 20）
   - 轉送模式可用 --transfer-mode zip|direct 切換（預設 zip）
   - FuTransfer 預設 protocol 為 HTTP（可用 --transfer-protocol http|batch）
   - HTTP 上傳預設埠：8080；批次串流預設埠：443（可用 --transfer-port 覆寫）
   - FuTransfer 壓縮可用 --transfer-compression gz|none（批次串流用）
   - HTTP 續傳設定：--transfer-no-resume / --transfer-clear-state
   - --transfer-http 為相容舊參數（等同 --transfer-protocol http）
   - Zip 暫存資料夾預設為 transfer_zips（zip 模式可用 --zip-root 指定）
   - 成功傳輸後會刪除 zip（zip 模式可用 --keep-zip 保留）
   - 可用 --no-clear 跳過清空 GENERAL（不建議）
   - 批次暫存 CSV 會定時清理（預設 24 小時，可用 --tmp-cleanup-hours / --cleanup-interval-minutes 調整）
   - Zip 暫存可選擇定時清理（--zip-cleanup-hours）
   - FuTransfer 伺服器端會定時清理 output 下的 .temp（可於 FuTransfer 的 transfer_config.py 調整）
   - 監控畫面：預設 http://localhost:8081（可用 --monitor-host / --monitor-port / --no-monitor 調整）
   - 完成後自動關機：--shutdown-after（預設成功才關機，可用 --shutdown-on-error 強制）
   - 關機延遲秒數：--shutdown-delay 60（可用 "shutdown /a" 取消）


3. 單筆查詢
   > run.bat --id PAT001 --date 2025-09-22 --modality CT --server LNK


4. 互動模式
   > run.bat
   依提示輸入查詢條件


5. 進階選項
   --timeout 180     覆寫下載逾時（秒）
   --debug          啟用詳細除錯日誌
   --config alt.yaml 使用替代設定檔


輸出
----
- 下載後的 DICOM 會儲存在：downloads\SERVER\DATE_PATIENTID_MODALITY\
- 日誌儲存在：logs\
- 下載失敗報告：failed_downloads_TIMESTAMP.txt


疑難排解
--------
1. 連線失敗：
   - 確認 config.yaml 內 IP 與 port
   - 檢查網路連線
   - 確認 PACS 伺服器已設定你的 AE Title

2. 查無資料：
   - 確認病人 ID 格式符合 PACS
   - 確認日期格式（YYYY-MM-DD）
   - 確認模態縮寫（CT, MR, MG 等）

3. 下載逾時：
   - 大型檢查可提高逾時（使用 --timeout）
   - 檢查網路速度
   - 確認 PACS 伺服器效能

4. 檔案缺漏：
   - 查看 failed_downloads 報告
   - 確認磁碟空間足夠
   - 檢查資料夾權限


伺服器設定
----------
PACS 管理者需要：
1. 將 "DICOM_DOWNLOADER" 加入允許的 AE Title
2. 設定允許從你的 IP 連線
3. 啟用 Query/Retrieve 服務


新增伺服器
----------
編輯 config.yaml 並加入新伺服器：

servers:
  NEW_SERVER:
    ae_title: "NEW_PACS"
    ip: "192.168.x.x"
    port: 11112
    description: "New Hospital PACS"


日誌檔案
--------
日誌內容包含：
- 連線嘗試
- 查詢參數
- 下載進度
- 錯誤訊息
- 逾時事件

除錯時可在 logs\ 資料夾查看日誌。


下載失敗報告
------------
每次執行後會產生報告，內容包含：
- 成功下載的檢查
- 失敗下載與原因
- 逾時失敗（供人工處理）
- 整體成功率


備註
----
- 連線失敗會自動重試（可於設定檔調整）
- 下載逾時超過 2 分鐘會被略過
- 所有 DICOM 皆以 SOP Instance UID 命名儲存
- 支援 CT、MR、MG 等 DICOM 模態


支援
----
如有問題：
1. 檢查 logs\ 資料夾內的日誌
2. 查看 failed_downloads 報告
3. 與 PACS 管理者確認伺服器設定
4. 確認網路連線


================================================================================
