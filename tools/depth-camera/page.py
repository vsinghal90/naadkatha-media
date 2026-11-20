import json
T=json.load(open('timeline.json'))
CAP={'d01':"Arjun ghabrahat se <i>kaanp</i> rahe the... aur Krishna <i>muskura</i> rahe the. <i>Kyun?</i>",
'd02':"<i>Kurukshetra</i> ka maidan. Saamne dushman nahi... <i>apne</i> the. Dada Bhishma... Guru Drona... apne bhai.",
'd03':"<i>Gita</i> ke pehle adhyay mein... Arjun khud Krishna se kehte hain:",
'd04':"“Krishna... mere haath-pair <i>dheele</i> pad rahe hain... munh sookh raha hai... mera mann <i>chakra</i> raha hai.”",
'd05':"“Apno ko maar kar... mujhe <i>jeet nahi chahiye</i>, Krishna.”",
'd06':"Arjun ne <i>dhanush</i> neeche rakh diya... aur rath mein baith gaye. Tab Krishna... <i>muskuraye</i>.",
'chant':"<i>Maatraa sparshaas tu Kaunteya, sheetoshna sukha duhkha daah; aagamaapaayino 'nityaas, taans titikshasva Bhaarata.</i>",
'd07':"Iska seedha <i>arth</i> hai:",
'd08':"“Arjun... sardi-garmi, sukh-dukh... ye <i>aate</i> hain, aur <i>chale jaate</i> hain. Ye tikte nahi... isliye inhe <i>dheeraj</i> se sah lo.”",
'd09':"Kisi bhi bade pal se pehle jo <i>ghabrahat</i> aapko hoti hai... wahi Arjun ko hui thi.",
'd10':"Dekha? Krishna isliye <i>muskuraye</i>... kyunki unhe pata tha: ghabrahat <i>aayi</i> hai, to <i>jaayegi</i> bhi.",
'd11':"<i>Aaj ye karke dekhiye:</i> jab dil ghabraye... das <i>gehri saansein</i> giniye, aur mann mein kahiye: “ye aayi hai, to jaayegi bhi.” Phir bas... agla ek <i>chhota kaam</i> kijiye.",
'd12':"Ye katha apne un <i>apno</i> ko bhejiye, jinke ye <i>kaam aa sakti</i> hai.",
'd13':"<span class='sm'>Agli katha (Gita 2.47):</span> Krishna ne kyun kaha, <i>phal ki chinta mat karo?</i>"}
WHO={'सूत्रधार':'Narrator','अर्जुन':'Arjun','कृष्ण':'Krishna'}
HI={'d01':"अर्जुन घबराहट से <i>काँप</i> रहे थे... और कृष्ण <i>मुस्कुरा</i> रहे थे। <i>क्यों?</i>",
'd02':"<i>कुरुक्षेत्र</i> का मैदान। सामने दुश्मन नहीं... <i>अपने</i> थे। दादा भीष्म... गुरु द्रोण... अपने भाई।",
'd03':"<i>गीता</i> के पहले अध्याय में... अर्जुन खुद कृष्ण से कहते हैं:",
'd04':"“कृष्ण... मेरे हाथ-पैर <i>ढीले</i> पड़ रहे हैं... मुँह सूख रहा है... मेरा मन <i>चकरा</i> रहा है।”",
'd05':"“अपनों को मार कर... मुझे <i>जीत नहीं चाहिए</i>, कृष्ण।”",
'd06':"अर्जुन ने <i>धनुष</i> नीचे रख दिया... और रथ में बैठ गए। तब कृष्ण... <i>मुस्कुराए</i>।",
'chant':"<i>मात्रास्पर्शास्तु कौन्तेय शीतोष्णसुखदुःखदाः। आगमापायिनोऽनित्यास्तांस्तितिक्षस्व भारत॥</i>",
'd07':"इसका सीधा <i>अर्थ</i> है:",
'd08':"“अर्जुन... सर्दी-गर्मी, सुख-दुख... ये <i>आते</i> हैं, और <i>चले जाते</i> हैं। ये टिकते नहीं... इसलिए इन्हें <i>धीरज</i> से सह लो।”",
'd09':"किसी भी बड़े पल से पहले जो <i>घबराहट</i> आपको होती है... वही अर्जुन को हुई थी।",
'd10':"देखा? कृष्ण इसलिए <i>मुस्कुराए</i>... क्योंकि उन्हें पता था: घबराहट <i>आई</i> है, तो <i>जाएगी</i> भी।",
'd11':"<i>आज ये करके देखिए:</i> जब दिल घबराए... दस <i>गहरी साँसें</i> गिनिए, और मन में कहिए: “ये आई है, तो जाएगी भी।” फिर बस... अगला एक <i>छोटा काम</i> कीजिए।",
'd12':"ये कथा अपने उन <i>अपनों</i> को भेजिए, जिनके ये <i>काम आ सकती</i> है।",
'd13':"<span class='sm'>अगली कथा (गीता 2.47):</span> कृष्ण ने क्यों कहा, <i>फल की चिंता मत करो?</i>"}
WHOH={'सूत्रधार':'सूत्रधार','अर्जुन':'अर्जुन','कृष्ण':'कृष्ण'}
for l in T['lines']: l['cap']=CAP[l['k']]; l['capH']=HI[l['k']]; l['whoE']=WHO[l['who']]
import sys
TPL=sys.argv[1] if len(sys.argv)>1 else 'page.tpl.html'; OUT=sys.argv[2] if len(sys.argv)>2 else 'preview/index.html'
open(OUT,'w').write(open(TPL).read().replace('__TL__',json.dumps(T,ensure_ascii=False)))
