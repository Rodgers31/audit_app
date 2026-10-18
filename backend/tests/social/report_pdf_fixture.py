"""Offline valid CoB-shaped table with two qualified categories per county."""
def multicategory_pdf(actual, publication_label):
    commands = []
    def label(x, y, value):
        value = value.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
        commands.append(f'BT /F1 7 Tf {x} {y} Td ({value}) Tj ET')
    label(25,810,'Controller of Budget County Budget Implementation Review FY2025/26 Annual')
    label(25,790,publication_label)
    columns = [20,130,260,390,520,660]
    for x in columns: commands.append(f'{x} 680 m {x} 760 l S')
    for y in [680,700,720,740,760]: commands.append(f'20 {y} m 660 {y} l S')
    headers = ['County','Allocated Total (Kshs.Million)','Absorbed Total (Kshs.Million)',
               'Recurrent Allocated (Kshs.Million)','Recurrent Absorbed (Kshs.Million)']
    for x,value in zip(columns,headers): label(x+3,747,value)
    for y,county,value in [(727,'Nairobi',actual),(707,'Mombasa','1'),(687,'Kisumu','1')]:
        for x,cell in zip(columns,[county,'10',value,'5',value]): label(x+3,y,cell)
    stream='\n'.join(commands).encode()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
             b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 700 850] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
             b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
             b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream']
    body,offsets=bytearray(b'%PDF-1.4\n'),[0]
    for number,obj in enumerate(objects,1):
        offsets.append(len(body));body.extend(f'{number} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(body);body.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]: body.extend(f'{offset:010d} 00000 n \n'.encode())
    body.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(body)
