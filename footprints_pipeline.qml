<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.44.12" styleCategories="AllStyleCategories">
  <renderer-v2 type="singleSymbol" symbollevels="0">
    <symbols>
      <symbol type="fill" name="0" clip_to_extent="1" alpha="1">
        <layer class="SimpleFill" pass="0" locked="0">
          <Option type="Map">
            <Option type="QString" name="color" value="0,229,255,35"/>
            <Option type="QString" name="outline_color" value="0,229,255,255"/>
            <Option type="QString" name="outline_style" value="solid"/>
            <Option type="QString" name="outline_width" value="0.6"/>
            <Option type="QString" name="outline_width_unit" value="MM"/>
            <Option type="QString" name="style" value="solid"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
  <labeling type="simple">
    <settings calloutType="simple">
      <text-style fontWordSpacing="0" fontSize="8" fontLetterSpacing="0" textColor="255,255,255,255" fontFamily="Arial" fontWeight="bold">
        <text-buffer bufferSize="1.2" bufferColor="0,0,0,200" bufferDraw="1"/>
      </text-style>
      <rule fieldName="filename"/>
    </settings>
  </labeling>
</qgis>
