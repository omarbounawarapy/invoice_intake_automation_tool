COUNTRY_CODES: dict[str, str] = {
    "Austria": "AT",
    "Germany": "DE",
    "United Kingdom": "GB",
    "France": "FR",
    "Switzerland": "CH",
    "Netherlands": "NL",
    "Norway": "NO",
    "Spain": "ES",
    "Estonia": "EE",
}


from .pdf_ingester import PdfIngester


class InvoiceIngester(PdfIngester) : 


    def extract_header(self, page):
        header =  self.extract_lines_after_anchor(
            page,
            "Invoice",
            4,
        )[0:4]
        if "CREDIT NOTE" in header :
            return header 
        else : return header[:-1]

    def extract_bill_to(self, page):
        return self.extract_lines_after_anchor(
            page,
            "Bill to",
            3,
        )

    def extract_terms(self, page):
        return self.extract_line_containing_anchor(
            page,
            "Payment terms",
        )

    def extract_bank(self, page):
        return self.extract_line_containing_anchor(
            page,
            "Bank:",
        )
    def extract_discount(self,page):
        try :
            try :
                return self.extract_line_containing_anchor(
                    page,
                    "Less"
                )
            except : 
                return self.extract_line_containing_anchor(
                                page,
                                "Discount"
                            )
            
        except :
            return None

    def extract_vat(self,page): 
        try :
            return self.extract_lines_containing_anchor(
                page,
                "VAT"
            )
        except: 
            return None
        

    def extract_rendered_total(self,page):
        try : 
          return  self.extract_line_containing_anchor(
            page,
            "TOTAL:",
        )
        except : 
            return self.extract_line_containing_anchor(
                page,
                "amount due"
            )



    def extract_subtotal(self,page):
        try : 
            sub =  self.extract_line_containing_anchor(
                page,
                "The subtotal"
            )
        except : 
            sub  = self.extract_line_containing_anchor(
                page,
                "Subtotal"
            )
        return sub