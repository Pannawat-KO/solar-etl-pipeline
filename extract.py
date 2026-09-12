import requests
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("NREL_API_KEY")

url = "https://developer.nlr.gov/api/pvwatts/v8.json"
params = {
    "api_key": api_key,
    "lat": 13.7563,
    "lon": 100.5018,
    "system_capacity": 4,
    "module_type": 0,
    "losses": 14,
    "array_type": 1,
    "tilt": 20,
    "azimuth": 180
}

response = requests.get(url, params=params)
data = response.json()

print(data)

import pandas as pd

months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

df = pd.DataFrame({
    'month': months,
    'ac_power_kwh': data['outputs']['ac_monthly'],
    'solar_radiation': data['outputs']['solrad_monthly']
})

print(df)
import sqlite3

conn = sqlite3.connect('solar_forecast.db')
df.to_sql('bangkok_monthly_forecast', conn, if_exists='replace', index=False)
conn.close()

print("บันทึกข้อมูลลง database เรียบร้อย")

df.to_json('solar_forecast.json', orient='records')
print("Export เป็น JSON เรียบร้อย")
# === เพิ่มใหม่: Export CSV + Upload ขึ้น S3 ===
import boto3
from datetime import datetime
from botocore.exceptions import ClientError, NoCredentialsError

# Export เป็น CSV (เพิ่มจาก JSON ที่มีอยู่แล้ว)
csv_filename = "solar_forecast.csv"
df.to_csv(csv_filename, index=False)
print(f"Export เป็น {csv_filename} เรียบร้อย")

# ตั้งชื่อไฟล์ปลายทางบน S3 ให้มี timestamp เพื่อเก็บ history แต่ละวัน
BUCKET_NAME = "solar-forecast-data-phuwanet"
today_str = datetime.now().strftime("%Y-%m-%d")
s3_key = f"solar_forecast/{today_str}.csv"

try:
    s3 = boto3.client("s3")
    s3.upload_file(csv_filename, BUCKET_NAME, s3_key)
    print(f"อัปโหลดขึ้น S3 สำเร็จ: s3://{BUCKET_NAME}/{s3_key}")
except NoCredentialsError:
    print("ERROR: ไม่พบ AWS credentials — เช็ค aws configure อีกครั้ง")
except ClientError as e:
    print(f"ERROR: อัปโหลด S3 ไม่สำเร็จ — {e}")