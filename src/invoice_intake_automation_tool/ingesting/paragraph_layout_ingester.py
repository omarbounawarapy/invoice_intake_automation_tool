from .invoice_ingester import InvoiceIngester
from pdfplumber import open as pdfopen


class ParagraphLayoutIngester(InvoiceIngester) : 
    def extract_items(self,page) : 
        try :
            lines = self.extract_between_anchors(page , "we invoice" , "VAT")


            items = []
            i = 0
            while i< len(lines) : 
                line = lines[i]
                if line[-1]=="." :
                    i+=1
                else :
                    line +=" "+ lines[i+1]
                    i+=2
                items.append(line)
            return items
        except : 
            return None
        
            






