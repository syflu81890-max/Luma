// One-time AST migration. Run only on untranslated source; idempotent per file.
const ts=require('typescript'),fs=require('fs'),path=require('path');
const dictionaryPath='locales/en.json';const catalog=new Set();
const sourceFiles=fs.readdirSync('src').filter(p=>/\.(ts|tsx)$/.test(p)&&p!=='i18n.ts').map(p=>'src/'+p);
const desktopFiles=['main.cjs','workspaces.cjs','x-session.cjs','browser-collector.cjs','completion.cjs','assistant.cjs','profile.cjs'].map(p=>'electron/'+p);
function keyFor(node){if(ts.isJsxText(node))return node.text.replace(/\s+/g,' ').trim();if(ts.isTemplateExpression(node))return node.head.text+node.templateSpans.map((s,i)=>'{'+i+'}'+s.literal.text).join('');return node.text||''}
for(const file of [...sourceFiles,...desktopFiles]){
 const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,file.endsWith('.tsx')?ts.ScriptKind.TSX:file.endsWith('.cjs')?ts.ScriptKind.JS:ts.ScriptKind.TS);
 const migrate=process.argv.includes('--apply')&&!/import \{ tr \}|const \{ tr \}/.test(source.text);let changed=false;
 const result=ts.transform(source,[context=>{
  const call=(key,values=[])=>{catalog.add(key);changed=true;return ts.factory.createCallExpression(ts.factory.createIdentifier('tr'),undefined,[ts.factory.createStringLiteral(key),...(values.length?[ts.factory.createArrayLiteralExpression(values)]:[])])};
  function visit(node){
   const key=keyFor(node);
   if(/[\u3400-\u9fff]/.test(key)){
    if(ts.isJsxText(node))return ts.factory.createJsxExpression(undefined,call(key));
    if(ts.isStringLiteral(node)||ts.isNoSubstitutionTemplateLiteral(node)){
     if(ts.isPropertyAssignment(node.parent)&&node.parent.name===node)return node;
     if(node.parent&&ts.isCallExpression(node.parent)&&node.parent.expression.getText(source)==='tr'){catalog.add(key);return node;}
     const translated=call(key);return node.parent&&ts.isJsxAttribute(node.parent)?ts.factory.createJsxExpression(undefined,translated):translated;
    }
    if(ts.isTemplateExpression(node))return call(key,node.templateSpans.map(s=>ts.visitNode(s.expression,visit)));
   }
   return ts.visitEachChild(node,visit,context);
  }
  return node=>ts.visitNode(node,visit);
 }]);
 if(migrate&&changed){let printed=ts.createPrinter({newLine:ts.NewLineKind.LineFeed}).printFile(result.transformed[0]);printed=(file.startsWith('src/')?"import { tr } from './i18n';\n":"const { tr } = require('./i18n.cjs');\n")+printed;fs.writeFileSync(file,printed)}
 result.dispose();
}
fs.mkdirSync('locales',{recursive:true});fs.writeFileSync('output/i18n-all-keys.json',JSON.stringify([...catalog],null,2));
if(!fs.existsSync(dictionaryPath))fs.writeFileSync(dictionaryPath,'{}\n');console.log('Translation keys:',catalog.size);
