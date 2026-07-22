import React, { useMemo, useRef, useCallback, useEffect, useState } from 'react';
import ForceGraph3D from 'react-force-graph-3d';

const ThreatGraph3D = ({ alerts, selectedIdentityId, setSelectedIdentityId, getSeverityColor }) => {
  const fgRef = useRef();
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

  const graphData = useMemo(() => {
    const nodes = new Map();
    const links = new Map();

    // Map all unique entities (Identity, IP, Cloud)
    alerts.forEach(a => {
      const idNode = a.identity;
      const ipNode = `ip-${a.source_ip}`;
      const cloudNode = `cloud-${a.cloud}`;

      // Identity Node (Red/Orange/Green based on max score)
      if (!nodes.has(idNode)) {
        nodes.set(idNode, { id: idNode, name: a.short_identity, type: 'identity', val: 5, maxScore: a.score });
      } else {
        if (a.score > nodes.get(idNode).maxScore) {
          nodes.get(idNode).maxScore = a.score;
        }
      }

      // IP Node (Gray)
      if (!nodes.has(ipNode)) {
        nodes.set(ipNode, { id: ipNode, name: a.source_ip, type: 'ip', val: 3, maxScore: 0 });
      }

      // Cloud Node (Blue)
      if (!nodes.has(cloudNode)) {
        nodes.set(cloudNode, { id: cloudNode, name: a.cloud, type: 'cloud', val: 8, maxScore: 0 });
      }

      // Links: Identity -> IP, Identity -> Cloud
      const link1 = `${idNode}->${ipNode}`;
      if (!links.has(link1)) {
        links.set(link1, { source: idNode, target: ipNode });
      }

      const link2 = `${idNode}->${cloudNode}`;
      if (!links.has(link2)) {
        links.set(link2, { source: idNode, target: cloudNode });
      }
    });

    return {
      nodes: Array.from(nodes.values()),
      links: Array.from(links.values())
    };
  }, [alerts]);

  const handleNodeClick = useCallback(node => {
    if (node.type === 'identity') {
      setSelectedIdentityId(node.id);
    }
  }, [setSelectedIdentityId]);

  return (
    <div ref={containerRef} style={{ flex: 1, position: 'relative', overflow: 'hidden', background: '#0f172a', borderRadius: '8px', margin: '0 1.5rem 1.5rem 1.5rem', boxShadow: 'inset 0 0 20px rgba(0,0,0,0.5)' }}>
      {dimensions.width > 0 && (
        <ForceGraph3D
          ref={fgRef}
          graphData={graphData}
          nodeLabel="name"
          nodeColor={node => {
            if (node.id === selectedIdentityId) return '#ffffff'; // Highlight selected
            if (node.type === 'identity') return getSeverityColor(node.maxScore);
            if (node.type === 'ip') return '#64748b'; // Gray
            if (node.type === 'cloud') return '#3b82f6'; // Blue
            return '#ffffff';
          }}
          nodeRelSize={1}
          nodeVal="val"
          linkColor={() => 'rgba(255,255,255,0.1)'}
          linkWidth={1}
          onNodeClick={handleNodeClick}
          backgroundColor="#0f172a"
          width={dimensions.width}
          height={dimensions.height}
        />
      )}
      <div style={{ position: 'absolute', top: 15, left: 15, color: 'rgba(255,255,255,0.8)', fontSize: '0.85rem', pointerEvents: 'none', background: 'rgba(0,0,0,0.5)', padding: '0.5rem', borderRadius: '4px' }}>
        <div style={{ marginBottom: 4 }}><span style={{ display: 'inline-block', width: 10, height: 10, background: '#ef4444', borderRadius: '50%', marginRight: 5 }}></span> Identities (Clickable)</div>
        <div style={{ marginBottom: 4 }}><span style={{ display: 'inline-block', width: 10, height: 10, background: '#64748b', borderRadius: '50%', marginRight: 5 }}></span> Source IPs</div>
        <div><span style={{ display: 'inline-block', width: 10, height: 10, background: '#3b82f6', borderRadius: '50%', marginRight: 5 }}></span> Cloud Environments</div>
      </div>
    </div>
  );
};

export default ThreatGraph3D;
