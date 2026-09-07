# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ops'))
import transferegov_csv_probe as probe


def test_current_publisher_name_resolves_only_exact_csv_member(tmp_path):
    path=tmp_path/'siconv_convenio.zip'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('siconv_convenio.csv','NR_CONVENIO;IND_ASSINADO\n123;SIM\n')
    result=probe.inspect_zip(path,'siconv_convenio.zip')
    assert result['archive_member']=='siconv_convenio.csv'
    assert result['selected_public_sample']==[{'NR_CONVENIO':'123','IND_ASSINADO':'SIM'}]
    assert probe.FILES==('siconv_convenio.zip','siconv_termo_aditivo.zip','siconv_desembolso.zip')
