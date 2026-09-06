// SPDX-License-Identifier: AGPL-3.0-or-later
export const MAP_TEXT={
  'pt-BR':{
    loading:'Carregando o mapa. A lista continua disponível.',
    updating:'Atualizando os pontos desta área…',
    retry:'Recarregar mapa',hide:'Fechar mapa',canvas:'Mapa interativo; os lugares também estão na lista',
    unavailable3D:'O estilo atual não fornece uma camada de edificações compatível com 3D.',
    zoom3D:'Aproxime até o nível 15 para ver volumes onde houver altura informada.',
    geometry3D:'Volumes da base cartográfica, não uma vistoria da obra ou retrato atual. Edificações sem altura informada não ganham uma altura inventada.',
    tileWarning:'Parte do mapa não carregou. A lista e os dados consultados continuam independentes da base cartográfica.',
    count:'registros georreferenciados carregados nesta área; agrupamentos não são novas unidades.',
    styleFailure:'Não foi possível preparar o mapa. Recarregue ou continue pela lista.',
  },
  en:{
    loading:'Loading the map. The list remains available.',updating:'Updating places in this area…',
    retry:'Reload map',hide:'Close map',canvas:'Interactive map; places are also available in the list',
    unavailable3D:'The current style does not provide a compatible 3D building layer.',
    zoom3D:'Zoom to level 15 to see volumes where a height is provided.',
    geometry3D:'Basemap volumes are not a works inspection or a current survey. Buildings without a supplied height do not receive an invented one.',
    tileWarning:'Some map content did not load. The list and queried records remain independent of the basemap.',
    count:'loaded geocoded records in this area; groups are not additional facilities.',
    styleFailure:'The map could not be prepared. Reload it or continue using the list.',
  },
  es:{
    loading:'Cargando el mapa. La lista sigue disponible.',updating:'Actualizando los puntos de esta zona…',
    retry:'Recargar mapa',hide:'Cerrar mapa',canvas:'Mapa interactivo; los lugares también están en la lista',
    unavailable3D:'El estilo actual no proporciona una capa de edificios compatible con 3D.',
    zoom3D:'Acerca hasta el nivel 15 para ver volúmenes donde se informe la altura.',
    geometry3D:'Los volúmenes del mapa no son una inspección de obras ni un levantamiento actual. No se inventan alturas para edificios que no las tengan.',
    tileWarning:'Parte del mapa no se cargó. La lista y los datos consultados son independientes del mapa base.',
    count:'registros georreferenciados cargados en esta zona; las agrupaciones no son unidades adicionales.',
    styleFailure:'No fue posible preparar el mapa. Recárgalo o continúa con la lista.',
  },
};
/** @param {string} locale @param {string} key */
export function mapText(locale,key){return (MAP_TEXT[locale]||MAP_TEXT['pt-BR'])[key]||key;}
