/**
 * =================================================================
 * メイン関数：管理表の各スプレッドシートからデータを取得し、全履歴シートに書き込む
 * ロジックを元コードに忠実に再現し、高速化対応を行った最終版
 *
 * 担当者: [ご自身の名前やチーム名]
 * 更新日: 2025/06/17
 * バージョン: 4.0
 * =================================================================
 */
function consolidateReports() {
  // --- 設定項目 ---
  const masterSpreadsheetUrl = "https://docs.google.com/spreadsheets/d/1fBNfkFBARSpT-OpLOytbAfoa0Xo5LTWv7irimssxcUU/edit?pli=1&gid=1935825846#gid=1935825846";
  const masterSheetName = "報告シート（「説明用」以外はタダメンMから関数生成）M";
  const urlColumn = "A";
  const startRow = 2;
  const skipUrl = "https://docs.google.com/spreadsheets/d/17PMx-smOoj2ZzsG7A6A4FGXEfxXiZGkukERXJc1Cbi0/edit"; // 【説明用】がスキップ対象

  // シートごとの設定を配列で定義
  // 元のコードでは最終行判定列は関数内でB列に固定されていたため、ここでの列指定は不要
  const sheetConfigs = [
    {
      reportSheetName: "【都度入力】業務報告",
      targetSheetName: "【都度入力】業務報告_全履歴data",
      dataStartRow: 7,
      dataEndColumn: "K"
    },
    {
      reportSheetName: "【月１入力】補助＆立替報告＋月締め",
      targetSheetName: "【月１入力】補助＆立替報告＋月締め_全履歴data",
      dataStartRow: 4,
      dataEndColumn: "K"
    }
  ];
  // --- 設定項目ここまで ---

  Logger.log("--- 処理開始：全スプレッドシートのデータ集約を開始します ---");

  try {
    // ステップ1: 管理表からURLリストを取得
    Logger.log("[ステップ1開始] 管理表からURLリストを取得します...");
    const masterSpreadsheet = SpreadsheetApp.openByUrl(masterSpreadsheetUrl);
    const masterSheet = masterSpreadsheet.getSheetByName(masterSheetName);
    if (!masterSheet) {
      throw new Error(`管理用のマスターシートが見つかりません。シート名: "${masterSheetName}"`);
    }
    const lastRowInMaster = masterSheet.getLastRow();
    if (lastRowInMaster < startRow) {
        Logger.log("[情報] 管理表に処理対象のURLが見つかりませんでした。処理を終了します。");
        return;
    }
    const urlRange = masterSheet.getRange(`${urlColumn}${startRow}:${urlColumn}${lastRowInMaster}`);
    const urls = urlRange.getValues().flat().filter(url => url && url !== skipUrl);
    Logger.log(`[ステップ1完了] 管理表から ${urls.length} 件のURLを取得しました。`);

    // ステップ2: 各URLを巡回し、データを収集
    const allData = {};
    sheetConfigs.forEach(config => {
      allData[config.targetSheetName] = [];
    });

    Logger.log("[ステップ2開始] 各スプレッドシートからのデータ収集を開始します...");

    urls.forEach((targetSpreadsheetUrl, index) => {
      const progress = `(${index + 1}/${urls.length})`;
      Logger.log(`--------------------------------------------------`);
      Logger.log(`[処理中 ${progress}] スプレッドシートを開いています: ${targetSpreadsheetUrl}`);

      try {
        const targetSpreadsheet = SpreadsheetApp.openByUrl(targetSpreadsheetUrl);

        sheetConfigs.forEach(config => {
          Logger.log(`  -> [シート検索] "${config.reportSheetName}"`);
          try {
            // getSheetData_ に渡す引数から不要な列指定を削除
            const data = getSheetData_(targetSpreadsheet, config.reportSheetName, config.dataStartRow, config.dataEndColumn);

            if (data.length > 0) {
              const dataWithUrl = data.map(row => [targetSpreadsheetUrl].concat(row));
              allData[config.targetSheetName] = allData[config.targetSheetName].concat(dataWithUrl);
              Logger.log(`    - [成功] ${data.length}行のデータを取得し、"${config.targetSheetName}" の集計に追加しました。 (現在の合計: ${allData[config.targetSheetName].length}行)`);
            } else {
              Logger.log(`    - [情報] データは0行でした。処理をスキップします。`);
            }
          } catch(sheetError) {
             Logger.log(`    - [シート単位のエラー] "${config.reportSheetName}" の処理中にエラーが発生しました。詳細: ${sheetError.message}`);
          }
        });
      } catch (error) {
        Logger.log(`  - [スプレッドシート単位のエラー] ${progress} このスプレッドシートの処理中にエラーが発生しました。次のURLへスキップします。詳細: ${error.message}`);
      }
    });

    Logger.log("--------------------------------------------------");
    Logger.log("[ステップ2完了] 全スプレッドシートからのデータ収集が完了しました。");

    // ステップ3: 収集したデータを全履歴シートに書き込む
    Logger.log("[ステップ3開始] 集約先シートへのデータ書き込みを開始します...");
    const writeSpreadsheet = SpreadsheetApp.openById("16V9fs2kf2IzxdVz1GOJHY9mR1MmGjbmwm5L0ECiMLrc");

    sheetConfigs.forEach(config => {
      const targetSheetName = config.targetSheetName;
      const targetSheet = writeSpreadsheet.getSheetByName(targetSheetName);
      const dataToWrite = allData[targetSheetName];

      Logger.log(`  -> [書き込み対象] "${targetSheetName}"`);

      if (targetSheet) {
        const existingLastRow = targetSheet.getLastRow();
        if (existingLastRow >= 2) {
          Logger.log(`    - [準備] 既存データ ${existingLastRow - 1} 行をクリアします。`);
          targetSheet.getRange(2, 1, existingLastRow - 1, targetSheet.getLastColumn()).clearContent();
        }

        if (dataToWrite.length > 0) {
          const numRows = dataToWrite.length;
          const numColumns = dataToWrite[0].length;
          Logger.log(`    - [書き込み実行] ${numRows} 行 x ${numColumns} 列 のデータを書き込みます...`);
          targetSheet.getRange(2, 1, numRows, numColumns).setValues(dataToWrite);
          Logger.log(`    - [書き込み完了] 正常に書き込まれました。`);
        } else {
          Logger.log(`    - [情報] 書き込むデータはありませんでした。`);
        }
      } else {
        Logger.log(`    - [重大なエラー] 書き込み先のシート "${targetSheetName}" が見つかりません！ このシートへの書き込みをスキップします。`);
      }
    });

    Logger.log("[ステップ3完了] データ書き込み処理が完了しました。");
    Logger.log("--- 全ての処理が正常に完了しました ---");

  } catch (e) {
    Logger.log(`!!!!!! プロセスが致命的なエラーにより中断されました !!!!!!`);
    Logger.log(`エラー詳細: ${e.message}`);
    Logger.log(`Stack Trace: ${e.stack}`);
  }
}

/**
 * シートデータ取得関数：指定されたスプレッドシートオブジェクトからデータを取得
 * @param {GoogleAppsScript.Spreadsheet.Spreadsheet} spreadsheet - 対象のスプレッドシートオブジェクト
 * @param {string} sheetName - データ取得元のシート名
 * @param {number} startRow - データ取得開始行
 * @param {string} endColumn - データ取得終了列（アルファベット）
 * @return {Array<Array<any>>} - 取得したデータの2次元配列。
 */
function getSheetData_(spreadsheet, sheetName, startRow, endColumn) {
  const sheet = spreadsheet.getSheetByName(sheetName);

  if (sheet) {
    // 元のコードの仕様に基づき、最終行は常にB列(列番号2)で判定する
    const lastRow = findLastRow_(sheet, 2);

    if (lastRow >= startRow) {
      const rangeA1Notation = `B${startRow}:${endColumn}${lastRow}`;
      const data = sheet.getRange(rangeA1Notation).getValues();
      
      // 元のコードのフィルタリング条件を再現
      const filteredData = data.filter(row => {
        return row[0] !== '' && row[0] != null && row[0] !== undefined;
      });
      
      return filteredData;
    } else {
      return [];
    }
  } else {
    return [];
  }
}

/**
 * 指定列の最終行を取得する（最終行から上方向にデータがあるセルを探索）
 * 元のコードの関数をそのまま使用します。
 * @param {GoogleAppsScript.Spreadsheet.Sheet} sheet - 対象のシートオブジェクト
 * @param {number} col - 列番号（1から始まる）
 * @return {number} - 最終行の行番号
 */
function findLastRow_(sheet, col) {
  const lastRow = sheet.getRange(sheet.getMaxRows(), col).getNextDataCell(SpreadsheetApp.Direction.UP).getRow();
  return lastRow;
}