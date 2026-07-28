import React, { useMemo, useRef, useEffect, useState, useCallback } from 'react';
import Globe from 'react-globe.gl';

const CITIES = [
  { lat: 40.7128, lng: -74.0060, name: "New York" },
  { lat: 51.5074, lng: -0.1278, name: "London" },
  { lat: 35.6762, lng: 139.6503, name: "Tokyo" },
  { lat: -33.8688, lng: 151.2093, name: "Sydney" },
  { lat: 55.7558, lng: 37.6173, name: "Moscow" },
  { lat: -23.5505, lng: -46.6333, name: "Sao Paulo" },
  { lat: 1.3521, lng: 103.8198, name: "Singapore" },
  { lat: 39.9042, lng: 116.4074, name: "Beijing" },
  { lat: 48.8566, lng: 2.3522, name: "Paris" },
  { lat: 28.6139, lng: 77.2090, name: "New Delhi" },
  { lat: 31.2304, lng: 121.4737, name: "Shanghai" },
  { lat: 37.7749, lng: -122.4194, name: "San Francisco" },
  { lat: 41.9028, lng: 12.4964, name: "Rome" },
  { lat: -1.2921, lng: 36.8219, name: "Nairobi" },
  { lat: 25.2048, lng: 55.2708, name: "Dubai" },
  { lat: 52.5200, lng: 13.4050, name: "Berlin" },
  { lat: 19.0760, lng: 72.8777, name: "Mumbai" },
  { lat: -34.6037, lng: -58.3816, name: "Buenos Aires" },
  { lat: -26.2041, lng: 28.0473, name: "Johannesburg" },
  { lat: 30.0444, lng: 31.2357, name: "Cairo" }
];

const stringToHash = (str) => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
};

const DC_LOCATION = { lat: 38.8951, lng: -77.0364 }; // Washington DC (HQ)

const ThreatGraphGlobe = ({ alerts, selectedIdentityId, setSelectedIdentityId, getSeverityColor }) => {
  const globeRef = useRef();
  const containerRef = useRef();
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useEffect(() => {
    if (containerRef.current) {
      const { clientWidth, clientHeight } = containerRef.current;
      setDimensions({ width: clientWidth, height: clientHeight });
      
      const handleResize = () => {
        setDimensions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
      };
      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
    }
  }, []);

  const { arcsData, ringsData } = useMemo(() => {
    const arcs = [];
    const ringsMap = new Map();

    // Only map the latest alert per identity to avoid drawing 1000 overlapping lines
    const latestPerIdentity = new Map();
    alerts.forEach(a => {
      if (!latestPerIdentity.has(a.identity)) {
        latestPerIdentity.set(a.identity, a);
      } else {
        const existing = latestPerIdentity.get(a.identity);
        if (new Date(a.timestamp) > new Date(existing.timestamp)) {
          latestPerIdentity.set(a.identity, a);
        }
        // Also keep track of max score for the identity
        if (a.score > existing.score) {
          existing.score = a.score;
        }
      }
    });

    Array.from(latestPerIdentity.values()).forEach(a => {
      const cityIdx = stringToHash(a.source_ip) % CITIES.length;
      const city = CITIES[cityIdx];
      const color = getSeverityColor(a.score);
      const isSelected = selectedIdentityId === a.identity;

      arcs.push({
        startLat: city.lat,
        startLng: city.lng,
        endLat: DC_LOCATION.lat,
        endLng: DC_LOCATION.lng,
        color: isSelected ? ['#ffffff', '#ffffff'] : [color, 'rgba(255,255,255,0.2)'],
        identity: a.identity,
        ip: a.source_ip
      });

      // Avoid drawing duplicate rings for the exact same location
      const ringKey = `${city.lat}-${city.lng}`;
      if (!ringsMap.has(ringKey) || isSelected) {
        ringsMap.set(ringKey, {
          lat: city.lat,
          lng: city.lng,
          color: isSelected ? '#ffffff' : color,
          maxR: isSelected ? 8 : 4,
          propagationSpeed: isSelected ? 2 : 1,
          repeatPeriod: isSelected ? 800 : 1200
        });
      }
    });

    return {
      arcsData: arcs,
      ringsData: Array.from(ringsMap.values())
    };
  }, [alerts, selectedIdentityId, getSeverityColor]);

  // Point camera at the center point between Europe and US
  useEffect(() => {
    if (globeRef.current) {
      globeRef.current.pointOfView({ lat: 30, lng: -40, altitude: 2 }, 1000);
    }
  }, []);

  const handleArcClick = useCallback(arc => {
    setSelectedIdentityId(arc.identity);
  }, [setSelectedIdentityId]);

  return (
    <div ref={containerRef} style={{ flex: 1, position: 'relative', overflow: 'hidden', background: '#000000', borderRadius: '8px', margin: '0 1.5rem 1.5rem 1.5rem', boxShadow: 'inset 0 0 20px rgba(0,0,0,0.8)' }}>
      {dimensions.width > 0 && (
        <Globe
          ref={globeRef}
          width={dimensions.width}
          height={dimensions.height}
          globeImageUrl="//unpkg.com/three-globe/example/img/earth-dark.jpg"
          backgroundColor="#000000"
          arcsData={arcsData}
          arcStartLat={d => d.startLat}
          arcStartLng={d => d.startLng}
          arcEndLat={d => d.endLat}
          arcEndLng={d => d.endLng}
          arcColor={d => d.color}
          arcDashLength={0.4}
          arcDashGap={4}
          arcDashInitialGap={() => Math.random() * 5}
          arcDashAnimateTime={2000}
          onArcClick={handleArcClick}
          arcLabel={d => `Threat Source: ${d.ip}`}
          
          ringsData={ringsData}
          ringColor={d => d.color}
          ringMaxRadius={d => d.maxR}
          ringPropagationSpeed={d => d.propagationSpeed}
          ringRepeatPeriod={d => d.repeatPeriod}
        />
      )}
      
      {/* Target Marker for HQ */}
      <div style={{ position: 'absolute', top: 15, left: 15, color: 'rgba(255,255,255,0.8)', fontSize: '0.85rem', pointerEvents: 'none', background: 'rgba(0,0,0,0.7)', padding: '0.5rem', borderRadius: '4px', border: '1px solid #333' }}>
        <div style={{ marginBottom: 4 }}><span style={{ display: 'inline-block', width: 10, height: 10, border: '2px solid #3b82f6', borderRadius: '50%', marginRight: 5 }}></span> Reference location</div>
        <div style={{ marginBottom: 4 }}><span style={{ display: 'inline-block', width: 10, height: 10, background: '#ef4444', borderRadius: '50%', marginRight: 5 }}></span> High-risk activity</div>
        <div style={{ fontSize: '0.7rem', color: '#aaa', marginTop: '0.5rem' }}>Select an arc to inspect the associated identity.</div>
      </div>
    </div>
  );
};

export default ThreatGraphGlobe;
