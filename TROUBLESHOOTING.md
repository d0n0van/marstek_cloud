# Troubleshooting Guide for Marstek Cloud Integration

## Common Issues and Solutions

### 1. Server Error (Code 500) - "系统错误，请稍后重试"

**Symptoms:**
- Error logs showing "Server error (code 500): 系统错误，请稍后重试"
- Integration appears offline intermittently
- Data updates fail sporadically

**Causes:**
- Marstek Cloud API server experiencing issues
- Network connectivity problems
- API rate limiting or overload

**Solutions:**

#### Immediate Actions:
1. **Check Marstek Cloud Status**: Visit the Marstek Cloud web interface to verify if their servers are operational
2. **Restart Home Assistant**: Sometimes a simple restart resolves temporary issues
3. **Check Network**: Ensure your Home Assistant instance has stable internet connectivity

#### Configuration Adjustments:
1. **Increase Scan Interval**: 
   - Go to Settings → Devices & Services → Marstek Cloud Battery → Configure
   - Increase the scan interval to 120-300 seconds (2-5 minutes)
   - This reduces API load and gives servers time to recover

2. **Enable Debug Logging**:
   ```yaml
   logger:
     default: warning
     logs:
       custom_components.marstek_cloud: debug
   ```

#### Advanced Troubleshooting:
1. **Run Debug Script**:
   ```bash
   python debug_integration.py
   ```
   This will test your API connection and show detailed error information.

2. **Check Home Assistant Logs**:
   - Look for patterns in error timing
   - Check if errors occur at specific times of day
   - Monitor network connectivity during errors

### 2. Sensor Update Taking Over 10 Seconds

**Symptoms:**
- Warning: "Update of sensor.mst_vnse3_a4c2_charge_power is taking over 10 seconds"
- Slow response times in Home Assistant
- Delayed data updates

**Causes:**
- Network latency to Marstek Cloud servers
- API server performance issues
- DNS resolution problems

**Solutions:**

#### Network Optimization:
1. **Check DNS Settings**: Ensure your Home Assistant instance uses reliable DNS servers (8.8.8.8, 1.1.1.1)
2. **Test Connectivity**:
   ```bash
   ping eu.hamedata.com
   nslookup eu.hamedata.com
   ```

#### Configuration Changes:
1. **Adjust Timeout Settings**: The integration now uses optimized timeouts:
   - Total timeout: 30 seconds
   - Connect timeout: 10 seconds
   - Socket read timeout: 15 seconds

2. **Enable Caching**: The integration caches data for 30 seconds to reduce API calls

### 3. Circuit Breaker Protection

The integration now includes a circuit breaker pattern to handle repeated server errors:

- **Threshold**: 3 consecutive server errors
- **Timeout**: 5 minutes before retrying
- **Fallback**: Returns cached data when circuit breaker is open

This prevents the integration from overwhelming the API during server issues.

### 4. Performance Monitoring

#### Diagnostic Sensors:
The integration provides these diagnostic sensors:
- `last_update`: Time of last successful update
- `api_latency`: API call duration in milliseconds
- `connection_status`: Online/offline status

Monitor these sensors to understand integration health.

#### Log Analysis:
Look for these log patterns:
- `Server error count: X/3` - Circuit breaker status
- `Circuit breaker open, returning cached data` - Using cached data
- `Resetting circuit breaker after successful request` - Recovery

### 5. Best Practices

1. **Regular Monitoring**: Check diagnostic sensors regularly
2. **Appropriate Scan Intervals**: Use 60-300 second intervals for most use cases
3. **Network Stability**: Ensure stable internet connection
4. **Log Management**: Enable debug logging only when troubleshooting

### 6. When to Contact Support

Contact Marstek support if:
- Server errors persist for more than 24 hours
- Integration is consistently offline
- Data appears incorrect or outdated

### 7. Integration Health Check

Run this Home Assistant script to check integration health:

```yaml
script:
  marstek_health_check:
    alias: "Marstek Health Check"
    sequence:
      - service: system_log.write
        data:
          message: "Marstek Integration Health Check"
          level: info
      - service: system_log.write
        data:
          message: "Connection Status: {{ states('sensor.mst_vnse3_a4c2_connection_status') }}"
          level: info
      - service: system_log.write
        data:
          message: "Last Update: {{ states('sensor.mst_vnse3_a4c2_last_update') }}"
          level: info
      - service: system_log.write
        data:
          message: "API Latency: {{ states('sensor.mst_vnse3_a4c2_api_latency') }}ms"
          level: info
```

Replace `mst_vnse3_a4c2` with your actual device name.

---

## Recent Improvements

The integration has been updated with:

1. **Enhanced Error Handling**: Better retry logic with exponential backoff
2. **Circuit Breaker Pattern**: Prevents API overload during server issues
3. **Connection Optimization**: Improved DNS resolution and connection pooling
4. **Timeout Improvements**: More granular timeout settings
5. **Caching**: 30-second data caching to reduce API load
6. **Diagnostic Sensors**: Better monitoring capabilities

These improvements should significantly reduce the frequency of server errors and improve overall reliability.
