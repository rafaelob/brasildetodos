# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import sys
import zipfile
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ops'))
import transferegov_csv_probe as probe


def test_inventory_ignores_paths_and_detects_more_pages():
    xml=b'<EnumerationResults><Blobs><Blob><Name>one.csv.zip</Name><Properties><Content-Length>123</Content-Length></Properties></Blob><Blob><Name>../bad</Name></Blob></Blobs><NextMarker>next</NextMarker></EnumerationResults>'
    entries,more=probe.parse_index(xml)
    assert len(entries)==1 and more and entries['one.csv.zip']['bytes']==123


@pytest.mark.parametrize('raw',[b'<!DOCTYPE root><x/>',b'<!ENTITY x "y"><x/>',b'<unexpected/>',b'<EnumerationResults><Blobs><Blob><Name>a.zip</Name><Properties><Content-Length>x</Content-Length></Properties></Blob></Blobs></EnumerationResults>'])
def test_invalid_xml_refused(raw):
    with pytest.raises(ValueError):probe.parse_index(raw)


def test_selected_fields_exclude_person_and_bank_information(tmp_path):
    path=tmp_path/'sample.zip'
    with zipfile.ZipFile(path,'w') as z:z.writestr('siconv_convenio.csv','NR_CONVENIO;VL_GLOBAL_CONV;CPF;CONTA\n123;100,00;private;private\n')
    result=probe.inspect_zip(path,'siconv_convenio.csv.zip')
    assert result['fields']==['NR_CONVENIO','VL_GLOBAL_CONV','CPF','CONTA']
    assert result['selected_public_sample']==[{'NR_CONVENIO':'123','VL_GLOBAL_CONV':'100,00'}]


@pytest.mark.parametrize('member',['../siconv_convenio.csv','wrong.csv'])
def test_unexpected_zip_members_refused(tmp_path,member):
    path=tmp_path/'sample.zip'
    with zipfile.ZipFile(path,'w') as z:z.writestr(member,'x')
    with pytest.raises(ValueError):probe.inspect_zip(path,'siconv_convenio.csv.zip')


def test_namespaced_inventory_keeps_exact_names_and_sizes():
    xml=b'<EnumerationResults xmlns="http://schemas.microsoft.com/windowsazure"><Blobs><Blob><Name>siconv_convenio.csv.zip</Name><Properties><Content-Length>100</Content-Length><Last-Modified>date</Last-Modified></Properties></Blob></Blobs></EnumerationResults>'
    result,more=probe.parse_index(xml)
    assert not more and result['siconv_convenio.csv.zip']['bytes']==100
