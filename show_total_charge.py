#!/usr/bin/env python3
"""Show Total Charge for all Marstek devices using .env credentials."""
import asyncio
import aiohttp
from marstek_cloud.coordinator import MarstekAPI
from dotenv import load_dotenv
import os

load_dotenv()

async def show_total_charge():
    """Display total charge for all devices."""
    print("🔋 Marstek Cloud - Total Charge Summary")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        api = MarstekAPI(session, os.getenv('MARSTEK_EMAIL'), os.getenv('MARSTEK_PASSWORD'))
        
        try:
            devices = await api.get_devices()
            
            total_charge = 0
            total_devices = len(devices)
            
            print(f"📊 Found {total_devices} device(s):")
            print()
            
            for i, device in enumerate(devices, 1):
                name = device.get('name', 'Unknown Device')
                devid = device.get('devid', 'Unknown ID')
                soc = device.get('soc', 0)
                charge = device.get('charge', 0)
                discharge = device.get('discharge', 0)
                
                # Calculate total charge (assuming 5.12 kWh capacity)
                capacity = 5.12  # kWh
                device_total_charge = (soc / 100) * capacity
                total_charge += device_total_charge
                
                print(f"🔋 Device {i}: {name}")
                print(f"   ID: {devid}")
                print(f"   SOC: {soc}%")
                print(f"   Charge: {charge}W")
                print(f"   Discharge: {discharge}W")
                print(f"   Total Charge: {device_total_charge:.2f} kWh")
                print()
            
            print("=" * 50)
            print(f"📈 TOTAL CHARGE ACROSS ALL DEVICES: {total_charge:.2f} kWh")
            print(f"📊 Average per device: {total_charge/total_devices:.2f} kWh")
            
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(show_total_charge())
