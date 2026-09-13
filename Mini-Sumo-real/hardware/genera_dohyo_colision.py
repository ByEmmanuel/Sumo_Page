"""Malla cerrada del dohyo, mismo radio/altura; evita Cylinder-Cylinder ODE."""
import math
from pathlib import Path

world=Path(__file__).resolve().parents[1]/'webots/worlds/dohyo.wbt'
s=world.read_text()
n=96  # resolución geométrica: error radial máximo 0.207 mm, inferior al jitter manual
points=[(0.385*math.cos(i*2*math.pi/n),0.385*math.sin(i*2*math.pi/n),z)
        for z in [-0.0125,0.0125] for i in range(n)]+[(0,0,-0.0125),(0,0,0.0125)]
faces=[]
for i in range(n):
    j=(i+1)%n
    faces += [(i,j,n+i),(j,n+j,n+i),(2*n,j,i),(2*n+1,n+i,n+j)]
mesh='IndexedFaceSet { coord Coordinate { point [ '+', '.join(' '.join(f'{v:.10f}' for v in p) for p in points)+' ] } coordIndex [ '+', '.join(' '.join(map(str,f))+' -1' for f in faces)+' ] }'
a=s.index('boundingObject ',s.index('DEF DOHYO '))+len('boundingObject ')
b=s.index('{',a);depth=1;i=b+1
while depth:
    depth+=(s[i]=='{')-(s[i]=='}');i+=1
world.write_text(s[:a]+mesh+s[i:])
