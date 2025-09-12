# Copilot Instructions for Marstek Cloud Battery Integration

This document provides guidance for AI coding agents working on the Marstek Cloud Battery custom integration for Home Assistant. It outlines the architecture, workflows, and conventions specific to this project.

---

## 📂 Project Overview

This integration connects Marstek battery systems to Home Assistant by interacting with the Marstek cloud API. It fetches live data and exposes it as sensor entities in Home Assistant.

### Key Components

- **`config_flow.py`**: Handles user input during setup (email, password, scan interval, battery capacities).
- **`__init__.py`**: Initializes the integration, including API client and data coordinator.
- **`coordinator.py`**: Manages periodic data updates using Home Assistant's `DataUpdateCoordinator`.
- **`sensor.py`**: Defines sensor entities for battery metrics and diagnostics.
- **`manifest.json`**: Metadata for Home Assistant to recognize the integration.

---

## 🔄 Data Flow

1. **Setup**: User provides credentials and configuration via `config_flow.py`.
2. **API Interaction**: The integration logs in to the Marstek API, retrieves a token, and fetches device data.
3. **Data Coordination**: `coordinator.py` schedules periodic updates and caches data.
4. **Entity Updates**: Sensor entities pull data from the coordinator and update Home Assistant.

---

## 🛠 Developer Workflows

### Testing the Integration

1. Copy the `marstek_cloud` folder into the `custom_components` directory of a Home Assistant installation.
2. Restart Home Assistant.
3. Add the integration via **Settings → Devices & Services → Add Integration**.
4. Use the Home Assistant logs to debug issues (`config/home-assistant.log`).

### Debugging API Calls

- Use the `MarstekAPI` class in `coordinator.py` to simulate API calls.
- Check the `api_latency` and `connection_status` diagnostic sensors for runtime insights.

---

## 📐 Project-Specific Conventions

- **Password Hashing**: Passwords are hashed using MD5 before being sent to the API.
- **Scan Interval**: Configurable between 10 and 3600 seconds.
- **Default Battery Capacity**: Set to 5.12 kWh unless overridden by the user.
- **Entity Naming**: Sensor entities use the format `devid_fieldname` for unique IDs.

---

## 🌐 API Endpoints

- **Login**: `POST https://eu.hamedata.com/app/Solar/v2_get_device.php`
- **Get Devices**: `GET https://eu.hamedata.com/ems/api/v1/getDeviceList`

---

## 🧩 Integration Patterns

- **Coordinator Pattern**: The `MarstekCoordinator` class centralizes data fetching and caching.
- **Entity Creation**: Each device metric is represented as a separate sensor entity, defined in `sensor.py`.
- **Retry Logic**: The API client retries login if the token expires.

---

## 📄 Key Files

- `custom_components/marstek_cloud/__init__.py`
- `custom_components/marstek_cloud/config_flow.py`
- `custom_components/marstek_cloud/coordinator.py`
- `custom_components/marstek_cloud/sensor.py`
- `custom_components/marstek_cloud/manifest.json`

---

For further details, refer to the [README.md](../README.md).