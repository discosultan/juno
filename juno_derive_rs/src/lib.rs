use proc_macro::TokenStream;
use quote::quote;
use syn::{parse_macro_input, ItemStruct};

#[proc_macro_derive(Chromosome)]
pub fn derive_chromosome(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as ItemStruct);

    let name = &input.ident;
    let (impl_generics, ty_generics, where_clause) = input.generics.split_for_impl();
    let field_count = input.fields.iter().count();
    let field_name_1 = input.fields.iter().map(|field| &field.ident);
    let field_name_2 = input.fields.iter().map(|field| &field.ident);
    let index_2 = input.fields.iter().enumerate().map(|(i, _)| i);
    let field_name_3 = input.fields.iter().map(|field| &field.ident);
    let index_3 = input.fields.iter().enumerate().map(|(i, _)| i);

    let output = quote! {
        impl #impl_generics Chromosome for #name #ty_generics #where_clause {
            fn length() -> usize {
                #field_count
            }

            fn generate(rng: &mut StdRng) -> Self {
                Self {
                    #(
                        #field_name_1: #field_name_1(rng),
                    )*
                }
            }

            fn mutate(&mut self, rng: &mut StdRng, i: usize) {
                match i {
                    #(
                        #index_2 => self.#field_name_2 = #field_name_2(rng),
                    )*
                    _ => panic!("index out of bounds")
                };
            }

            fn cross(&mut self, parent: &Self, i: usize) {
                match i {
                    #(
                        #index_3 => self.#field_name_3 = parent.#field_name_3,
                    )*
                    _ => panic!("index out of bounds")
                };
            }
        }
    };

    TokenStream::from(output)
}
