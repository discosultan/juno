use syn::{Field, Meta, NestedMeta};

pub fn is_chromosome(field: &Field) -> bool {
    field
        .attrs
        .iter()
        .any(|attr| attr.path.is_ident("chromosome"))
}

pub fn is_serde_default(field: &Field) -> bool {
    field.attrs.iter().any(|attr| {
        if attr.path.is_ident("serde") {
            let meta = attr.parse_meta().unwrap();
            if let Meta::List(meta) = meta {
                if let NestedMeta::Meta(meta) = &meta.nested[0] {
                    if let Meta::Path(path) = meta {
                        if path.is_ident("default") {
                            return true;
                        }
                    }
                }
            }
        }
        false
    })
}

// Ref: https://rosettacode.org/wiki/Cartesian_product_of_two_or_more_lists#Rust
pub fn cartesian_product(lists: Vec<&[&'static str]>) -> Vec<Vec<&'static str>> {
    let mut res: Vec<Vec<&'static str>> = vec![];

    let mut list_iter = lists.iter();
    if let Some(first_list) = list_iter.next() {
        for i in *first_list {
            res.push(vec![*i]);
        }
    }
    for l in list_iter {
        let mut tmp = vec![];
        for r in res {
            for &el in *l {
                let mut tmp_el = r.clone();
                tmp_el.push(el);
                tmp.push(tmp_el);
            }
        }
        res = tmp;
    }
    res
}
