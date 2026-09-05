// Run with Node.js and @oai/artifact-tool available in the module search path.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { Workbook, SpreadsheetFile } = require('@oai/artifact-tool');
const root = process.cwd();
await fs.mkdir(path.join(root,'tmp'),{recursive:true});
const data = JSON.parse(await fs.readFile(path.join(root,'results/tables/primary_weekly_workbook_data.json'),'utf8'));
const wb = Workbook.create();
const notes = wb.worksheets.add('口径说明');
notes.showGridLines=false;
notes.getRange('A1:B1').values=[['主模型每周配置','Improved Convex Adaptive Global RRP']];
const items=data.notes.slice(1).map((s,i)=>[String(i+1),s]);
items.push(['数据来源','primary_weekly_summary.csv / primary_weekly_holdings.csv / primary_weekly_weights.csv']);
items.push(['记录范围',`${data.summary.length-1} 次调仓；${data.holdings.length-1} 条资产记录；每期 30 只 ETF`]);
items.push(['使用方法','每周收益按自然周排列；每周持仓可按调仓日或 ETF 筛选；权重矩阵按日期逐行核对。']);
notes.getRangeByIndexes(1,0,items.length,2).values=items;
notes.getRange('A:A').format.columnWidth=22;
notes.getRange('B:B').format.columnWidth=100;
notes.getRangeByIndexes(0,0,items.length+1,2).format.rowHeight=34;
notes.getRangeByIndexes(0,0,items.length+1,2).format.wrapText=true;
const headings={
 week_start:'自然周起点',week_end:'自然周终点',actual_week_start:'首个交易日',rebalance_date:'调仓日',information_cutoff:'信息截止日',trading_days:'周内交易日数',calendar_week_gross_return:'自然周毛收益',calendar_week_net_return:'自然周净收益',turnover:'调仓换手',transaction_cost:'交易成本',holding_period_end:'持有期末日',holding_period_days:'持有交易日数',holding_period_net_return:'新持仓期间净收益',calendar_week_at_sample_end:'样本末周',holding_period_truncated:'持有期截断',cash_target_weight:'现金目标权重',max_target_weight:'最大单资产权重',ticker:'ETF 代码',asset:'ETF 名称',asset_class:'资产类别',pretrade_weight:'交易前漂移权重',target_weight:'调仓目标权重',weight_change:'权重变化',absolute_trade_weight:'绝对交易权重'};
for(const [key,title,tableName] of [['summary','每周收益','WeeklyReturns'],['holdings','每周持仓','WeeklyHoldings'],['weights','权重矩阵','WeeklyWeights']]){
 const matrix=data[key], headers=matrix[0];
 const rows=matrix.slice(1).map(r=>r.map(v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)?new Date(v+'T00:00:00Z'):v));
 const sheet=wb.worksheets.add(title);sheet.showGridLines=false;
 const range=sheet.getRangeByIndexes(0,0,matrix.length,headers.length);
 range.values=[headers.map(h=>headings[h]??h),...rows];
 range.format.font={name:'Microsoft YaHei',size:10};
 range.format.columnWidth=19;range.format.rowHeight=22;
 const header=sheet.getRangeByIndexes(0,0,1,headers.length);
 header.format.fill='#17324D';header.format.font={bold:true,color:'#FFFFFF'};header.format.rowHeight=34;
 for(let j=0;j<headers.length;j++){
  const col=sheet.getRangeByIndexes(1,j,rows.length,1),h=headers[j];
  if(rows[0][j] instanceof Date)col.setNumberFormat('yyyy-mm-dd');
  else if(typeof rows[0][j]==='number')col.setNumberFormat(/days/.test(h)?'0':/cost/.test(h)?'0.000000%':'0.0000%');
 }
 const table=sheet.tables.add(range.address,true,tableName);
 table.showFilterButton=true;
 sheet.freezePanes.freezeRows(1);
}
notes.getRange('A1:B1').format.fill='#17324D';
notes.getRange('A1:B1').format.font={name:'Microsoft YaHei',bold:true,color:'#FFFFFF',size:12};
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(root,'results/tables/primary_weekly_holdings.xlsx'));
console.log(await wb.inspect({kind:'region',sheetId:'每周持仓',range:'A1:K3',maxChars:1800}));
const preview=await wb.render({sheetName:'口径说明',range:'A1:B11',scale:1.5,format:'png'});
await fs.writeFile(path.join(root,'tmp/weekly_workbook_preview.png'),new Uint8Array(await preview.arrayBuffer()));
const sample=await wb.render({sheetName:'每周持仓',range:'A1:K7',scale:1.2,format:'png'});
await fs.writeFile(path.join(root,'tmp/weekly_holdings_preview.png'),new Uint8Array(await sample.arrayBuffer()));
console.log('Exported all weekly records to primary_weekly_holdings.xlsx');
