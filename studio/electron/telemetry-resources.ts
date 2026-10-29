/** The sender, builder and packaged-resource gate use one active wire format. */
const telemetryWireName = 'wire-v3'
export const telemetryWireResource = `telemetry-${telemetryWireName}.json`
export const telemetryResourceNames = Object.freeze([
  'disclosure', 'catalog', 'desktop-origins', telemetryWireName, 'transport-route',
])
