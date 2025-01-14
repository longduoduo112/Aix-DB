<script setup>
***REMOVED***
import { Transformer ***REMOVED*** from 'markmap-lib'
import { Markmap ***REMOVED*** from 'markmap-view'

const transformer = new Transformer(***REMOVED***
const initValue = `# 思维导图\n1. 标题1\n - 子标题1\n - 子标题2\n2. 标题2\n3. 标题3`
const mm = ref(***REMOVED***
const svgRef = ref(***REMOVED***

const update = (***REMOVED*** => {
    const { root ***REMOVED*** = transformer.transform(initValue***REMOVED***
    mm.value.setData(root***REMOVED***
    mm.value.fit(***REMOVED***
***REMOVED***

onMounted((***REMOVED*** => {
    mm.value = Markmap.create(svgRef.value***REMOVED***
    update(***REMOVED***
***REMOVED******REMOVED***
const loading = ref(false***REMOVED***
***REMOVED***
***REMOVED***
    <LayoutCenterPanel :loading="loading">
        <template #sidebar>
  ***REMOVED***flex="~ col" h-full style="background-color: #f6f7fb">
      ***REMOVED***flex="~ justify-between items-center">
                    <NavigationNavBar />
    ***REMOVED***

      ***REMOVED***flex="1 ~ col" min-h-0 pb-20>
          ***REMOVED***class="mind">
                        <div
                            class="svg-container"
                            style="height: 100%; width: 100%"
              ***REMOVED***
                            <svg
                                ref="svgRef"
                                style="
                                ***REMOVED***
                                  ***REMOVED***
                                  ***REMOVED***
                                "
                  ***REMOVED***</svg>
            ***REMOVED***
        ***REMOVED***
    ***REMOVED***
***REMOVED***
        ***REMOVED***
    </LayoutCenterPanel>
***REMOVED***

***REMOVED***
html,
body,
.mind {
    margin: 0;
  ***REMOVED***
  ***REMOVED***
    overflow: hidden;
***REMOVED***
.mind {
  ***REMOVED***
    justify-content: center;
    align-items: center;
***REMOVED***
***REMOVED***
